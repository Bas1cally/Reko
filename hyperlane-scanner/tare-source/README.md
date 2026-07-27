# Tare contest source — local copy

Contest: Sherlock `tare-io__tare-contracts`, 20–29 Jul 2026, 50,000 USDC.
Upstream: `sherlock-audit/2026-07-tare-DERFUEHRER21` → subfolder `tare-io__tare-contracts/`.

## Why this directory exists

The execution container is recycled between sessions. A clone under `~/` does **not** survive, and
GitHub access from the agent side is scoped to `bas1cally/reko` only — the Sherlock fork cannot be
read directly. Anything not committed here has to be re-supplied by hand, which cost most of a
session once already. Files land here as they are obtained.

## Present

- `contracts/LoansNFT.sol` — complete. The `_update` nonce logic is what
  `../findings/tare-navstart-permanent-freeze/` rests on.
- `contracts/LoansExchange.sol` — complete. Read this together with `LoansNFT.sol`, not separately:
  `lock` clearing the ERC-721 approval and `createOffer` locking immediately only cancel out when
  both are in view. A lead was written up and retracted for exactly that reason.

## Not present (re-supply before relying on any claim about them)

`PortfolioVault.sol`, `NavCalculator.sol`, `Loans.sol`, `SECURITY.md` — all four were read in full
and are quoted where they matter in the findings, but are **deliberately not hand-transcribed here**.
A 600–900 line file retyped from a chat transcript can pick up silent corruption, and a subtly wrong
archived source is more dangerous than an absent one: it reads as authoritative. Get these in via the
git route below, which copies bytes.

Also missing: `LoansLedger.sol`, `LoansAuth.sol`, `VaultShareToken.sol`, `TrustedCalls.sol`,
`TrustedSpender.sol`, `SmartAccountFactory.sol`, `Rescuable.sol`, `GuardianAccessControl.sol`,
`interfaces/`, `specs/`.

Note on `Loans.sol`: an earlier version supplied in this engagement was demonstrably **not** the
contest version — `SECURITY.md` references `investorWithdrawByUnlocker` and `receiveBorrowerPayment`,
neither of which existed in it, and #26 describes `applyWaterfall`'s gating in the future tense. The
version read on 2026-07-27 *is* the contest one (it has `investorWithdraw` with the unlocker branch
inlined, `pay()`, and `applyWaterfall` gated `onlyOutstandingOrFullyPaid`). Findings written before
that date against the older paste should be re-checked.

## Cheapest way to fill the gaps

The whole tree can be committed in one shot rather than pasted file by file. A local commit already
exists at `~/reko-tmp` (`4078640`, "Add Tare contest source for review") containing
`contracts/` + `specs/` + `SECURITY.md`; it failed to push only because the stored GitHub credential
authenticates as `DERFUEHRER21` while the repo is owned by `Bas1cally` (403). Clearing the
`git:https://github.com` entry from Windows Credential Manager and re-authenticating as the repo
owner makes that one push land the entire source tree here.
