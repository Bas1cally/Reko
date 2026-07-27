# Tare — where things actually stand after `SECURITY.md`

## What changed

Real repo access revealed `SECURITY.md` (31 numbered known issues, 10 trust assumptions, 9 design
tradeoffs) and `specs/invariants.md` (a formally tagged E/D/C/O property catalogue). This is an
unusually mature security posture for a $50k contest — closer to what a $1M+ program publishes.
Both findings developed in this session from source alone (`Rescuable` currency drain, the
`LoansNFT` lock-based theft path) turned out to already be documented (#2 and #1 respectively). That
is a good sign about the quality of the analysis and a bad sign about the odds of finding something
genuinely new by continuing to read code the same way.

## What NOT to do

Don't re-derive anything already in the 31-item list or the trust-assumption section (T-1..T-10).
Read `SECURITY.md` in full before spending time on any new hypothesis — it is short enough (31
items) to hold in your head, and it directly names the file/function for each one.

## The one lead worth pursuing, in the team's own words

`specs/invariants.md`, §6 PortfolioVault:

> "**The master freshness invariant** (vault.md): *every* state affecting NAV — curated list, NFT
> holdings, idle USDC, loan ledger, `loans` pointer, calculator config — invalidates the cached NAV
> before the next `approveDeposit`/`approveRedemption`. It's maintained by a *manual conjunction*
> (nonce check + version check + explicit `_invalidateNav()` at each mutating call site + `maxNavAge`).
> **This is the highest-value property to fuzz: each new vault function must remember to invalidate,
> and a single omission is invisible until mispricing happens.**"

That is the team explicitly saying "we maintain this by remembering to call a function in N places;
we have not verified we always do." That is a genuinely open question, not a documented issue — the
31-item list has no entry for "function X forgets to invalidate NAV."

### Concrete next step

Read `PortfolioVault.sol` (601 lines, not yet reviewed this session) function by function. For
every external/public function that touches any of: the curated loan-ID list, NFT holdings,
`loans`/`loansNFT` pointers, `assetToken` balance-affecting operations, or calculator config —
check whether it calls `_invalidateNav()` (or equivalent) before returning. The bug shape to look
for: a function that mutates one of those five inputs but returns without invalidating, so a stale
`lastNav` continues to be used by the next `approveDeposit`/`approveRedemption` even though the true
NAV has changed. `NavCalculator.sol` (94 lines) is the second read — smaller, check it against
`invariants.md` §7's clamping/version-bump claims specifically (e.g. does `setMaxPortfolioFactor`
really only bump `configurationVersion` "when it clamps," as claimed — an unconditional-vs-conditional
bump mismatch there is exactly the kind of subtle gap this document's own style suggests is plausible).

### Secondary candidates, lower priority

- §6's "paired emptiness" invariant (`claimableDepositAssets[c] == 0 ⟺ claimableDepositShares[c] == 0`)
  — "a violation permanently strands the residual." Worth a quick check once `PortfolioVault.sol` is
  in hand, but this is explicitly called "preserved by floor math" by the team, i.e. they believe it
  holds — lower expected value than the freshness invariant, which they explicitly flag as unverified.
- §4's `ownershipNonce` — already independently verified sound on the `LoansNFT` side this session
  (unconditional bump in `_update`). If pursuing this, the remaining question is entirely on the
  `PortfolioVault` side: does `_requireFreshNav` actually compare the nonce it should, for every
  code path that reads it.

## Practical note

Both `PortfolioVault.sol` and `NavCalculator.sol` are now available directly from the real repo
(`~/2026-07-tare-DERFUEHRER21/tare-io__tare-contracts/contracts/`) — no more copy-pasting needed.
`cat contracts/PortfolioVault.sol` locally and paste it in, or read it there directly if continuing
the review yourself.
