# Push Chain Core Contracts SC — permissionless-surface sweep

Program: HackenProof "Push Chain — Core Contracts SC" ($10k, 7 submissions).
Repo: `pushchain/push-chain-core-contracts` @ `86e20e2` (main, 2026-03-17,
aligns with the "Last audit: Hacken — Mar 2026" note). Scope also names
`programs/pushsolanalocker/src/lib.rs` and `IAMMInterface.sol`, which live in a
separate repo (see "Unreachable asset" below).

Method: read `docs/THREAT_MODELLING_DOC.md` first (12 contracts, full STRIDE
tables, two disclosed findings F-01/F-02 + "additional observations"), then hunt
the crook shape it does NOT cover: a permissionless writer/initializer to state
that gates funds, a one-way lock an outsider trips, or sig-verify that fails open.

## Contracts read in full
- `src/uea/UEA_EVM.sol` (322 L) — ECDSA EIP-712 execute
- `src/uea/UEA_SVM.sol` (339 L) — Ed25519 precompile execute
- `src/uea/UEAFactory.sol` (294 L) — CREATE2 deploy + registry
- `src/PRC20.sol` (261 L) — custom synthetic ERC-20

## Crook hypotheses tested — all closed
1. **UEA account-hijack via permissionless `initialize`** (top hypothesis).
   `UEA_EVM/SVM.initialize(id, factory)` is guarded only by a `bool _initialized`
   (not OZ `initializer`) and is externally callable. IF `deployUEA` deployed the
   proxy without atomically initializing it, an attacker could initialize a
   victim's freshly-cloned UEA with `owner = attacker` and drain everything sent
   to that address. **Closed:** `UEAFactory.deployUEA` (`:180-187`) does
   `cloneDeterministic(salt)` → `initializeUEA(impl)` → `initialize(_id, this)`
   **atomically in one tx**, and the CREATE2 salt is `keccak256(abi.encode(_id))`
   — the address is derived from the *full* id including `owner`, so an
   attacker-owner id produces a *different* address. There is no victim-address /
   attacker-owner pairing. No hijack window.
2. **Signature replay within a deployment.** `getUniversalPayloadHash` binds the
   contract-storage `nonce`; `_handleExecution` does `nonce++`. Same signature
   never verifies twice. Closed. (Cross-*deployment* replay is disclosed F-02.)
3. **Signed-payload mutation.** EIP-712 struct binds `to`, `value`,
   `keccak256(data)`, gas fields, `nonce`, `deadline`, `vType`. Multicall
   `to/value/data` live inside `data`, so they are covered by the hash. Nothing
   executable is left unsigned. Closed.
4. **UEA_SVM Ed25519 fail-open.** `_verifySignatureSVM` staticcalls the
   precompile and `revert`s on `!success`, then `abi.decode(result,(bool))`.
   Fails **closed** on every error path (revert or false). No fail-open. Closed.
5. **ECDSA `recover` == address(0) match.** OZ `ECDSA.recover` reverts on a
   malformed/zero signature (does not return address(0)), so an `owner == 0`
   match is impossible. Closed.
6. **PRC20 permissionless mint / reentrancy.** `deposit` (mint) is gated to
   `UNIVERSAL_CORE`/`UE_MODULE`; `burn` only burns caller's own balance;
   `transferFrom` reverts-and-unwinds on low allowance with no external hook.
   No permissionless inflation or reentrancy. Closed.
7. **UEAProxy slot-0 / OZ Initializable overlap** (additional-observation).
   Re-init would need slot 0 to read zero after `initialize`; `_universalAccountId`
   starts with a non-empty `chainNamespace` for any registered chain, so slot 0
   is non-zero. An empty namespace would require an admin-registered empty chain
   — not permissionless. Closed.

## Verdict
The reachable in-scope core Solidity (UEA_EVM/SVM, UEAFactory, PRC20; and
UniversalCore, whose entire surface is `onlyUEModule`/`onlyGatewayPC`/
`onlyManager`/`onlyAdmin` per the threat-model access table) is clean for a
permissionless Critical **beyond the two already-disclosed findings** F-01 (CEA
missing ERC20 approval → ERC20 lock) and F-02 (domain separator omits
`block.chainid` → cross-deployment replay). Both are documented in the repo's own
threat model, hence out of scope under "known issues."

## Unreachable asset — the real smell
`programs/pushsolanalocker/src/lib.rs` (Solana/Anchor, in scope) is **not covered
by the project threat model at all** — the single highest crook-smell (in-scope +
zero coverage + a fund-locking custody program + Rust = our proven SVM toolchain).
An *old* `pushsolanalocker` existed in `push-chain-gateway-contracts` history at
`contracts/svm-gateway/programs/pushsolanalocker/` but was deleted ("remove old
svm locker", commit d20d006) — a removed contract is not "currently deployed", so
not a valid target. The current in-scope copy (scope path `programs/pushsolanalocker
/src/lib.rs`, root-level `programs/`, alongside `src/interfaces/IAMMInterface.sol`)
is in a repo not present in the public `pushchain` org listing — likely private or
under an un-guessed name. **Need: the exact repo URL from the HackenProof "Assets
in Scope" link for `pushsolanalocker`.**
