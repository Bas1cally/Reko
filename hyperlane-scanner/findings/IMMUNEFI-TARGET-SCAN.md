# Immunefi program scan — where a real bug could actually pay

Scanned all **547** programs from the community mirror
([`infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial`](https://github.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial))
because immunefi.com 403s automated fetches. **Unofficial data — verify any
target on the official page before investing time.**

## The filter, and why

Hyperlane failed on scope, not on effort: its assets are 138 deployed EVM
addresses, no repository is an asset, and it explicitly invalidates bugs in
"demonstrably unused" code. Every hour spent on Solana/CosmWasm/Starknet there
was unpayable by rule.

So the filter is: **GitHub repositories must be in-scope assets**, program open
and not invite-only, and no clause that kills source-level findings.

| Cut | Programs |
|---|---|
| Total | 547 |
| ≥1 GitHub asset | 182 |
| …and open, not invite-only | 139 |
| …and ≥$250k, whole-repo assets, recent | the shortlist below |

Second filter, from what actually worked this session: the one genuine defect
found (Cairo FastTokenRouter) was in the **newest code, with zero tests, in a
language the audit crowd mostly skips**. Bounty size alone is a bad signal —
the $10M+ programs are the most picked-over code on earth.

## Top picks

### 1. Kamino — $1,500,000, Solana/Rust, launched Oct 2025

```
github.com/Kamino-Finance/klend     (lending)
github.com/Kamino-Finance/kvault    (vaults)
github.com/Kamino-Finance/scope     (oracle)
github.com/Kamino-Finance/kfarms    (farms)
```

- **Whole repositories** are `smart_contract` assets — plus the deployed
  program IDs, so source *and* deployment are covered.
- Highest bounty of any recently-launched program by 3x.
- Lending + vaults + an in-house oracle is the richest bug surface in DeFi:
  liquidation edge cases, interest-accrual rounding, vault share inflation,
  oracle staleness/confidence handling, and the interactions between the four.
- No out-of-scope text in the mirrored data — no Hyperlane-style trap.
- KYC required.

### 2. 1inch Smart Contracts — $500,000, launched **June 2026**

```
github.com/1inch/limit-order-protocol
github.com/1inch/fusion-protocol
github.com/1inch/cross-chain-swap
github.com/1inch/solana-crosschain-protocol   ← newest surface
github.com/1inch/solana-fusion                ← newest surface
github.com/1inch/token-plugins
github.com/1inch/farming
github.com/1inch/delegating
```

- **The newest program on Immunefi** — roughly one month old. Least
  researcher-hours spent, by definition.
- All 8 assets are **whole repos**.
- The two Solana repos are the standout: brand-new Solana code from a team whose
  expertise is EVM. Cross-chain atomic swap logic (escrow timelocks, secret
  reveal, refund paths) written in an unfamiliar execution model is exactly the
  combination that produced this session's real finding.

### 3. Firedancer / Frankendancer — $500,000, C/C++ + Rust, Solana validator

- Thin competition: most bounty hunters don't read C.
- Memory-safety class bugs, not Solidity-logic bugs.
- Counterpoint: Jump fuzzes this heavily in-house, and a payout needs
  consensus-level impact. High skill floor, high effort.

### 4. Stellar — $250,000, 10 whole repos, C/C++ + Rust L1

Large multi-repo surface, unusual language mix, modest bounty.

## What to skip, and why

| Program | Bounty | Why not |
|---|---|---|
| LayerZero | $15M | Launched 2023, Solidity, the most-hunted bridge code there is |
| Sky (ex-Maker) | $10M | `dss` has been audited continuously since 2017 |
| Reserve | $10M | Launched 2023, file-level assets, heavily covered |
| Aave / Compound | $1M | Reference implementations; effectively saturated |
| Sparklend | $5M | Mostly Aave-v3 forks — same saturation inherited |

Big bounty ≠ good odds. It usually means the opposite: the number is high
*because* everyone has already looked.

## Honest expectation

None of this makes finding a payable bug likely. Mature protocols with $500k+
bounties are audited repeatedly and hunted continuously. The realistic edge is
narrow: newest code, weakest test coverage, least-familiar language for that
team. Kamino's oracle/vault interactions and 1inch's two Solana repos fit that
profile better than anything else on the list.

If nothing surfaces after a serious pass, that is the normal outcome and worth
saying plainly rather than padding a report.
