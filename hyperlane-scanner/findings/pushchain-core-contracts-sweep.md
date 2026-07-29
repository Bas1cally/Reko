# Push Chain Core Contracts SC — full sweep at the exact scope commit

Program: HackenProof "Push Chain — Core Contracts SC" ($10k, 7 submissions).
**Scope repo/commit (authoritative, from the program page):**
`pushchain/push-chain-core-contracts` @ **`a2b61850d765679aa9e1e39998a47a348404bc08`**
("bug-fix-l1 setter functions", 2026-05-07). Private repo; the session git proxy
has read access (unauth browser gets 404/403).

> Note: `pushsolanalocker` / `IAMMInterface` were a red herring from a mixed
> asset paste — they are NOT in this program's scope. The real scope is the 15
> Solidity files below, all in this repo at this commit.

## In-scope assets (all read at a2b61850)
CEA.sol, CEAFactory.sol, CEAMigration.sol, CEAProxy.sol, PRC20.sol, UEA_EVM.sol,
UEA_SVM.sol, UEAFactory.sol, UEAMigration.sol, UEAProxy.sol, UniversalCore.sol,
WPC.sol, Utils.sol, Types.sol, Errors.sol.

## Key fact: this is a POST-FIX commit
Both findings disclosed in the repo's own `THREAT_MODELLING_DOC.md` are already
FIXED at a2b61850:
- **F-02** (UEA domain separator omitted Push Chain id → cross-deployment replay):
  fixed — `domainSeparator()` now encodes `bytes32(block.chainid)` as the EIP-712
  `salt` in both UEA_EVM (`:94`) and UEA_SVM (`:101`).
- **F-01** (CEA ERC20 outbound missing approval → token lock): fixed —
  `CEA.sendUniversalTxToUEA` now does `approve(gateway, amount)` → call →
  `approve(gateway, 0)` (`CEA.sol:142-144`).

Re-submitting either would be a known/fixed dupe → out of scope.

## Permissionless surface — the only Critical-eligible attack class
Critical here requires "no privileged role." At a2b61850 the *only* permissionless
entrypoints are: `UEAFactory.deployUEA`, `UEA.executeUniversalTx` (sig path),
`UEA.initialize`, PRC20 (`burn`/`transfer`/`approve`), WPC (`deposit`/`withdraw`),
and `UniversalCore.receive()`. Everything else (all of CEA/CEAFactory, every
UniversalCore operational fn and setter, the migrations) is gated to
VAULT / UNIVERSAL_EXECUTOR_MODULE / gatewayPC / an admin role — privileged, hence
not Critical-eligible, and "rogue privileged users" are explicitly out of scope.

## Crook hypotheses tested at a2b61850 — all closed
1. **UEA/CEA account-hijack via permissionless `initialize`.** Both
   `UEAFactory.deployUEA` (`:201-208`) and `CEAFactory.deployCEA` (`:178-185`)
   do clone → proxy-init → logic-init **atomically in one tx**, and the CREATE2
   salt is `keccak256(id)` / `keccak256(pushAccount)` — the address is derived
   from the owner identity, so there is no victim-address / attacker-owner pair
   and no pre-init window (no code at the address before the atomic deploy).
2. **Signature replay / mutation (UEA).** Struct hash binds `to`,`value`,
   `keccak(data)`, gas fields, storage `nonce`, `deadline`, `vType`; domain binds
   source chainId + this proxy + `block.chainid`. `executeUniversalTx` also checks
   `payload.nonce == nonce`. Same sig never verifies twice; multicall targets live
   inside signed `data`. Closed.
3. **UEA_SVM Ed25519 fail-open.** `_verifySignatureSVM` reverts on `!success`,
   else `abi.decode(result,(bool))` — fails closed on every path. Closed.
4. **Proxy logic-slot takeover.** `UEAProxy.initializeUEA` / `CEAProxy` are
   OZ-`initializer` + slot-empty guarded; OZ v5 Initializable uses namespaced
   storage (no slot-0 overlap with `_universalAccountId`). `UEAMigration` /
   `CEAMigration` are `onlyDelegateCall` and write only their **immutable**
   implementation addresses — a hostile delegatecall corrupts only the attacker's
   own slot; a victim UEA migrates only via owner-signed payload to the
   admin-fixed migration contract. Closed.
5. **UniversalCore swap value-conservation.** `swapAndBurnGas` (`:223`) holds
   `msg.value == amountInUsed + refund`, `nonReentrant`, WPC withdraw is CEI-safe;
   refund goes to gatewayPC-supplied `caller`. No stranded/extractable value.
6. **PRC20 / WPC.** PRC20 `deposit`(mint) gated to CORE/UE-module; `burn` only
   caller's balance; `transferFrom` reverts-and-unwinds with no hook. WPC is a
   CEI-safe WETH clone (balance decremented before the value call). Closed.
7. **`stringToExactUInt256` collision.** Rejects non-digits/empty, checked-math
   overflow revert. "01" vs "1" collide numerically but produce different salts →
   different proxy addresses → different domain separators; chain registration is
   admin-gated anyway. Closed.

## Verdict
At the exact scope commit `a2b61850`, the in-scope Core Contracts are **clean for
a permissionless Critical**, and both disclosed findings are already fixed. This
is a post-audit, post-fix codebase (Hacken Mar 2026). No fantasy finding will be
manufactured (standing rule: real bugs only).
