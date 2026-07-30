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
