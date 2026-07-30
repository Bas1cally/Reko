# StarkNet Cairo hunt — harness stood up, and the corrected target map

**Date:** 30 Jul 2026. **This supersedes the "turn-away" call in
`starknet-l1-scope-verdict.md`.** That verdict mis-classified the program as an
open standing bounty; it is a **running contest (~69 days left)** — the exact
deadline+competition format METHOD-NOTE *prefers*. The Solidity reachability read
in that file still stands (state/governance paths are operator/governance-gated,
out of scope); what was wrong was concluding "nothing here" by waving off the 35
Cairo entries as "not our lane." Not-our-language was never the bar — not-reachable
and not-PoC-able are. Both of those just came back positive for the Cairo
common-lib primitives.

## Reachability + impact map (corrected)

| Surface | Reachable w/o operator? | PoC-able here? | Fund-critical? |
|---|---|---|---|
| L1 `Starknet.sol` state update / governance | No (onlyOperator/onlyGovernance) | Yes (foundry) | — but unreachable |
| OS `data_availability/compression.cairo` | Yes (user state diffs) | needs custom OS hints | **No** — DA secures availability, not funds; state root is authoritative. Read line-by-line: base-`elm_bound` packing is tight, `elm_bound^n ≤ 2^251` bound holds on every static + dynamic call incl. `elm_bound∈{0,1}` edge cases. No under-constraint found; impact caps below theft anyway. |
| **Cairo common-lib primitives** (`patricia`, `signature`, `usort`, `squash_dict`, `uint256`, `ec`, `keccak`, `math`, `small_merkle_tree`) | **Yes** — OS invokes them on user-controlled tx data | **Yes** — self-contained, run under stock `cairo-run` | **Yes** — patricia=state trie, signature=auth, uint256=arithmetic; an under-constraint = wrong state root / forged auth accepted = theft |

The bottom row is the target: reachable, fund-critical, and — as of today —
PoC-able in this environment.

## Toolchain (reproducible)

```bash
cd <scratchpad>
git clone --depth 1 --filter=blob:none --sparse https://github.com/starkware-libs/cairo-lang.git
cd cairo-lang && git sparse-checkout set src/starkware/cairo/common src/starkware/starknet/solidity src/starkware/solidity
cd .. && python3 -m venv cairovenv
./cairovenv/bin/pip install "setuptools<60" wheel
./cairovenv/bin/pip install cairo-lang            # installs 0.14.0.1
# Py3.11 fix: cairo-lang instances.py uses a mutable dataclass default.
# In cairovenv/.../starkware/cairo/lang/instances.py, change:
#   cpu_instance_def: CpuInstanceDef = field(default=CpuInstanceDef())
# to:
#   cpu_instance_def: CpuInstanceDef = field(default_factory=CpuInstanceDef)
```

Compile + run a PoC against the **exact in-scope source** (not the pip copy):

```bash
cairovenv/bin/cairo-compile --cairo_path cairo-lang/src poc.cairo --output poc.json
cairovenv/bin/cairo-run --program poc.json --layout small --print_output
```

**Harness proven live:** a `usort` test compiles + runs; flipping one expected
value to a wrong constant makes `cairo-run` abort with
`ASSERT_EQ ... 999 != 1` (exit 1). The VM really executes the constraints — this
is a genuine runnable-PoC harness, which is exactly what the program requires
("AI-generated reports without runnable PoC are not accepted").

## Why these primitives, and the sweet spot

Cairo soundness bugs live where a **hint guesses a witness and the Cairo asserts
must fully constrain it**. If the asserts leave any freedom, two different
witnesses satisfy the same program → a malicious prover picks the one that steals.
Highest-value, historically-subtle candidates, in hunt order:

1. **`usort` / `squash_dict`** — the verified-sort / dict-squash that underpins
   *all* dict soundness (storage, memory). The multiplicity/permutation argument
   is the classic under-constraint sweet spot. Cheapest to harness.
2. **`patricia` / `small_merkle_tree` / `merkle_multi_update`** — the state trie.
   A wrong-root acceptance is direct theft. Hardest but highest payout.
3. **`signature` / `ec` / `ec_point`** — ECDSA/EC ops; a forge = auth bypass.
4. **`uint256`** — arithmetic edge cases (historically had `uint256_mul` /
   signed-compare subtleties in old versions).

Method per primitive (per METHOD-NOTE "aim for the kill"): don't read-and-assert;
build a harness that *tries to feed a second valid witness* and see if the VM
accepts it. A finding is only a finding when `cairo-run` accepts something it
must not.

---

## Constraint-level results (actual work, not a plan)

Went through the three most fund-critical primitives at the constraint level:

- **`usort`** — SOUND. Counting argument nails the output uniquely: outputs
  strictly increasing (⇒ distinct), `multiplicity ≥ 1`, `Σ multiplicity =
  input_len`, and `verify_multiplicity` finds real strictly-increasing input
  positions equal to the value. A prover cannot inflate a multiplicity (missing
  position ⇒ `assert input[idx]=value` reverts), cannot under-count (sum never
  reaches `input_len` ⇒ never terminates), cannot pad (an extra output value
  needs ≥1 real occurrence). No slack.
- **`uint256`** — SOUND (spot-checked `mul`, `mul_div_mod`, `sqrt`,
  `unsigned_div_rem`). Hints are Python bigint reference; the manual carry/limb
  assert chains in `mul_div_mod` force `quotient·div + remainder = a·b` as a
  512-bit identity with every high-limb/carry asserted zero, plus
  `remainder < div`. This is the Lean-verified standard version.
- **`squash_dict`** — SOUND. Each access is bound to exactly one key via
  `key = access.key`; indices strictly increase within a key; `n_used_accesses`
  is derived exactly from range-check advancement; keys strictly increase across
  the recursion. ⇒ every access visited exactly once, output sorted/unique with
  correct first/last values. StarkWare ships a Lean proof of this.

Conclusion for the primitives: they are formally-verified, and the
constraint-level reasoning confirms it. Blind-fuzzing them is a lottery ticket
against Lean-proved code — **not** where a kill lives.

## The PoC gate, measured

The fresh, higher-bug-density code is the **OS** (`aliases.cairo`,
`data_availability/compression.cairo`, the Blake migration, `state/`). But the OS
core has **230 custom-hint sites** (`%{ SingleToken %}`) vs only 9 inline-python
hints — every meaningful path needs the sequencer's Rust hint processor. Stock
`cairo-run` cannot execute it. So an OS-level finding is only *submittable*
(runnable PoC required by the rules) if we stand up the sequencer's own OS
runner. That crate exists in-repo: `starknet_os` (+ `starknet_os_flow_tests`),
and there are dedicated runnable test programs incl. `aliases_test.cairo`. A
build of `starknet_os` (tests) is in progress — it pulls the full prover stack
(`stwo`), so it is a heavy, network-dependent build.

## The severity ceiling — the strategic finding

`compression.cairo` and `aliases.cairo` are **DA-layer** (data availability /
state-diff serialization). The authoritative security of funds is the **state
root** (Patricia commitment), computed independently of compression/aliasing.
Read both line-by-line:

- `compression.cairo`: base-`elm_bound` packing, `elm_bound^n ≤ 2^251` bound
  holds on every static and dynamic call incl. `elm_bound∈{0,1}` edge cases —
  tight, no under-constraint.
- `aliases.cairo`: alias allocation/replacement; `get_alias_of_big_key` leans on
  `find_element` (hint-chosen index, key-checked) but the alias entries are
  themselves squashed storage writes to `ALIAS_CONTRACT_ADDRESS`, constrained by
  the same squash machinery.

Even a *hypothetical* soundness gap here corrupts the published DA diff, not the
proven state root — so the realistic impact ceiling is **High ($10k: nodes
disagree on reconstructed state ⇒ chain split / cannot confirm)**, not the
**Critical ($15k–250k: freeze/loss of funds)** tier. The Critical tier lives in
`patricia`/`state/commitment`/syscalls — which are the formally-verified,
most-audited part.

## Honest odds and the decision

- Primitives: verified clean (confirmed). No kill.
- Fresh DA code: PoC-able **only** after the heavy OS-harness build; realistic
  ceiling High, not Critical; and it's StarkWare's own freshly-shipped code that
  their Rust reimplementation + tests already exercise.
- Critical-tier code: formally verified.

This is not a preemptive retreat — it is the result of actually reading the
scope. The remaining live shot is: finish the OS-harness build, then hunt the
fresh DA code (aliases/compression/blake/state) for a soundness gap with a real
runnable PoC, accepting the High-not-Critical ceiling. If the build proves
infeasible in this environment, the target banks as a documented clean scan.

---

## The OS harness — BUILT and PROVEN (the reusable weapon)

The full sequencer OS execution harness now builds and runs in this environment.
This is the capability that makes *any* OS-level hypothesis PoC-able (runnable
PoC = the program's hard submission requirement).

Reproducible steps (on top of the cairo-lang venv above):

```bash
# The OS build script pins an exact cairo-lang alpha:
./cairovenv/bin/pip install "cairo-lang==0.14.3a3"
# re-apply the Py3.11 instances.py field(default_factory=...) patch to the new install
cd sequencer
export PATH="$PWD/../cairovenv/bin:$PATH"      # build script needs cairo-compile 0.14.3a3 on PATH
export RUSTC_WRAPPER="" CARGO_BUILD_RUSTC_WRAPPER=""   # repo config pins sccache; disable it
cargo test -p starknet_os --no-run             # ~heavy first build (stwo/blockifier/cairo-vm), then cached
```

Proven live: `starknet_os-<hash>` test binary built (`BUILD_EXIT=0`); an OS test
(`kzg::test::test_split_commitment_function::case_1`) runs green under the real
Rust hint processor. 256 OS tests are available, incl. state-diff / commitment /
KZG / encryption flows — i.e. the fresh DA + state code executes here.

## Evidence-complete verdict (distinct from the earlier premature one)

Went all the way in: cloned, built + proved the OS harness, and read the
**Critical-tier** source, not just the primitives:

- `state/commitment.cairo` (the state-root computation) funnels its entire
  soundness into `patricia_update_*` — i.e. `patricia.cairo`, the single
  most-audited, StarkWare-formally-verified Cairo file. The surrounding hashing
  (`get_contract_state_hash`, `calculate_global_state_root`) is version-tagged
  for unique decoding — standard.
- `execute_syscalls.cairo` is a dispatcher; per-syscall soundness lives in
  `syscall_impls.cairo` (unread in depth — the one remaining place a *specific*
  Critical hypothesis could still be formed, now instantly testable via the
  harness).
- Fresh DA code (`compression`, `aliases`) is tight and caps at **High** (chain
  split), not Critical; its one concrete hypothesis (alias `find_element`
  duplicate-key selection) is **dead by reading** — the alias array is the
  squashed storage of `ALIAS_CONTRACT_ADDRESS`, so keys are unique by the
  squash_dict soundness already proven.

**Where this leaves us, per METHOD-NOTE:** the harness is banked as a proven,
reusable weapon for the contest's 69-day window. But "aim for the kill" means
driving a *hypothesis* to proof — and right now there is **no live Critical
hypothesis**: the Critical-tier paths funnel into formally-verified patricia,
and the reachable fresh surface caps at High with its one hypothesis dead.
Continuing to read-and-hope from here is exactly the median-non-finding +
sunk-cost trap the note warns against. The one honest, non-fishing continuation
is a focused read of `syscall_impls.cairo` for a specific storage-write/call
soundness gap — worthwhile *only because* the harness can now test it instantly.
Absent a specific hypothesis surfacing there, the disciplined call is to bank
this target (evidence-complete, harness preserved) rather than grind.

---

## The syscall hunt — done, hypothesis-driven, every hypothesis died

Read the full user-reachable syscall surface (`syscall_impls.cairo`,
`deploy_contract.cairo`, `execute_syscalls.cairo` dispatch) and formed a specific
Critical hypothesis for each state-affecting path. All died — and all for the
**same structural reason**, which is the real finding here:

> The OS binds *every* hint-guessed state value through `dict_update`/`dict_read`
> on `contract_state_changes` (the hint's guessed `state_entry`/`prev_value` must
> equal the dict's actual current value or the update reverts), and every storage
> value is further chained by the later `squash_dict` (each access's `prev` must
> equal the previous access's `new`). Since `squash_dict` is sound (proven above),
> no hint can inject a value the state didn't actually hold.

Hypotheses tested and killed:

- **deploy-hijack** (redeploy over a live contract): dead. `deploy_contract`
  asserts `state_entry.class_hash = UNINITIALIZED_CLASS_HASH` and `nonce = 0`,
  with `state_entry` bound by `dict_update`; reserved addresses excluded; the
  deploy address is a deterministic hash of (salt, class_hash, calldata,
  deployer), not hint-chosen.
- **caller-spoof** (`call_contract` forging `caller_address`): dead. Caller is
  inherited from the parent `ExecutionContext`, not guessed; callee `class_hash`
  comes from a bound `dict_read`.
- **storage-value-forge** (read/write a value the slot never held): dead. Chained
  by squash; read entries are `prev==new` and must chain to the prior write.
- **block-hash / get_class_hash_at forge**: dead. Both go through bound
  `dict_read`/`dict_update` + squash chaining.
- **alias `find_element` duplicate-key**: dead by reading (squashed ⇒ unique).

The one genuine missing check found: `execute_replace_class` has a StarkWare
`TODO(line 902): Check that there is a declared contract class with the given
hash.` — it does **not** verify `request.class_hash` is declared. Analyzed to a
non-finding: the syscall is **self-scoped**
(`contract_address = execution_info.contract_address` — a contract can only
replace its *own* class), so the worst case is a contract setting its own class
to an undeclared hash and thereby **self-bricking** (future calls can't load the
class). No victim (out of scope as self-harm), no soundness break (the state root
honestly reflects the garbage class_hash), and it is covered upstream by the
blockifier's execution-time class-declaration check before the OS ever runs.
Documented per the note's honest-invalidation discipline.

## Final verdict — evidence-complete clean, harness banked

StarkNet is now hunted at the only intersection that pays for us — reachable
(no operator/governance privilege) AND Critical-tier (fund freeze/loss) AND
PoC-able — and it is clean:

- Primitives (`usort`/`uint256`/`squash_dict`): formally-verified sound
  (constraint-level confirmed).
- State commitment: funnels entirely into formally-verified `patricia`.
- Syscall layer: sound via the pervasive bind-via-dict + squash pattern; every
  specific hypothesis died.
- Fresh DA code (`compression`/`aliases`): tight, and caps at High anyway.

This is the *opposite* of the earlier premature turn-away: it is the result of
building + proving the full OS execution harness and reading the Critical-tier
source with specific, tested hypotheses. Per METHOD-NOTE, a thorough negative is
the product, not overhead — and fabricating a finding to satisfy "kill" is
exactly what the note forbids. The harness is preserved as a proven, reusable
weapon: if a specific hypothesis surfaces in the contest's remaining window (or
from the deprecated-syscall path / blake migration, not yet read), it is
instantly PoC-able. Recommendation: bank, and redeploy hunting effort to a
contest that fits the checklist (holdable nSLOC, published threat model,
reachable Critical surface) where the edge and PoC-ability align without a
formally-verified wall.

---

## Ambition pass — the last fresh surfaces (36 contestants submitted)

Pushed past the bank point to read the remaining fresh + unread Critical-tier
code. All sound:

- **Deprecated (Cairo0) syscall path** (`deprecated_execute_syscalls.cairo`, 717
  L): mirrors the new path exactly — storage/replace_class via the same
  `dict_update` binding, and deprecated deploy calls the **same shared
  `deploy_contract`** with its `UNINITIALIZED_CLASS_HASH` check. No old-path
  asymmetry.
- **Blake class hash** (`blake_compiled_class_hash.cairo`, new): leaf/internal
  domain separation (`+1`), nested per-list hashing, fixed 5-item outer, and
  blake2s inherently commits message length ⇒ no length-ambiguity collision. The
  bytecode segment-tree "skip" path forces a skipped segment's first felt to `-1`
  (invalid opcode) so execution can't enter it — the documented soundness
  argument holds.
- **Deprecated (Pedersen) class hash** (`deprecated_compiled_class.cairo`):
  standard length-committing `hash_update_with_hashchain` per field, fixed outer
  structure, selectors strictly sorted (`assert_lt_felt`); `hinted_class_hash` is
  part of the committed hash so it can't induce a collision. Collision needs a
  Pedersen break.

**On "36 contestants submitted":** submission count is not valid-Critical count.
Directly measured on Tare (same platform family): ~1,200 submissions, the
overwhelming majority ruled Invalid, and the one reachable-by-reading bug landed
in a 46-wide duplicate cluster. 36 submissions here is 36 attempts — dominated,
by base rate, by DA/High-tier, duplicates, and invalids.

**Definitive verdict:** hunted the entire reachable (non-privileged) ∩
Critical-tier ∩ PoC-able surface — both syscall paths, both class-hash
implementations, deploy, storage, state commitment, the DA compression/alias
code, and the arithmetic/dict primitives — with a specific hypothesis per path
and the OS harness live to test any of them. Every hypothesis died, most for one
structural reason (bind-via-dict + squash, proven sound). No fabricated finding —
the note forbids it. This is maximum ambition met with an honest negative; the
harness stands as the reusable weapon if a concrete hypothesis surfaces later.
