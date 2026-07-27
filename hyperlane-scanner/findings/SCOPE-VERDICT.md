# Immunefi scope check — verdict on both findings

**Checked**: July 2026. **Both findings are outside the payable scope.** Details
and reasoning below, so the conclusion can be re-verified rather than trusted.

## Source and its limitation

`immunefi.com` and `docs.hyperlane.xyz` both return HTTP 403 to automated
fetches (Cloudflare bot protection), so the official scope page could not be
read directly. The data below comes from
[`infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial`](https://github.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial),
a bot-maintained mirror that commits Immunefi policy/scope changes as JSON.

**This mirror is unofficial and may be stale.** Confirm on
https://immunefi.com/bug-bounty/hyperlane/scope/ in a normal browser before
acting on this. That said, the conclusions below rest on two independent
grounds each, so a small mirror drift would not overturn them.

## What is actually in scope

| | |
|---|---|
| **Asset types** | exactly two: `smart_contract` and `websites_and_applications` |
| **Smart contracts** | **138 deployed contract addresses**, given as block-explorer links (Mailbox proxy/impl, ISMs, hooks, ValidatorAnnounce) |
| **Chains** | Arbitrum, Avalanche, Base, BSC, Celo, Ethereum, Gnosis, Moonbeam, Optimism, Polygon — **all EVM** |
| **Web** | `usenexus.org`, `hyperlane.xyz` |
| **GitHub repositories** | **none — not a single repo is listed as an asset** |
| **Absent chains** | **Starknet, Solana/Sealevel, CosmWasm do not appear anywhere** |

The scope is **address-based, not repository-based.** "Core repositories on the
Hyperlane GitHub" is not how this program is actually scoped — only specific
deployed addresses count.

## Two policy clauses that decide both findings

> "Vulnerabilities in components that exist in the codebase but are demonstrably
> unused or not integrated with production systems will be classified as
> **invalid**."

> Out of scope: "Attacks requiring access to privileged addresses (governance,
> owner, etc)."

## Verdict: `starknet-fast-router-filler-loss`

**Out of scope — on two independent grounds.**

1. **Starknet is not an in-scope chain.** No Starknet asset appears; the scope
   is 10 EVM chains plus two websites. `hyperlane-starknet` is not listed and
   no repository is.
2. **Even setting that aside**, the FastTokenRouter is *demonstrably unused* —
   I verified no deployment exists in `hyperlane-registry` and no artifact ships
   in the monorepo. That matches the "demonstrably unused" clause word for word,
   which classifies it **invalid**, not merely low severity.

Do not submit this to Immunefi. See "Still worth reporting" below.

## Verdict: `multisig-duplicate-validator`

**Almost certainly invalid**, though on softer ground than the Starknet one.

- The deployed EVM multisig ISMs *are* in-scope assets, so unlike the Starknet
  finding it clears the asset hurdle.
- **But** producing the vulnerable state requires an owner to deploy or
  configure a validator set containing a duplicate. That is squarely
  "attacks requiring access to privileged addresses (governance, owner, etc)",
  which is explicitly out of scope.
- **And** I verified that no deployed set contains a duplicate (1,964 validator
  sets, 3,940 addresses, zero duplicates), so the vulnerable configuration is
  itself "demonstrably unused".

Expect rejection. If submitted at all, submit it as Informational with no
economic-damage claim, and expect it to be closed on the privileged-access
clause.

## What this means for finding something payable

The real target surface is narrower than assumed at the start of this work:
**138 specific deployed EVM contracts** — Mailbox (proxy and implementation),
ISMs, hooks, ValidatorAnnounce — on 10 chains, plus two web apps.

In-scope Critical impacts named by the program:

- Direct theft of funds
- Unauthorized minting of interchain assets
- Protocol insolvency

Implications for how to search:

- Non-EVM implementations (Solana, CosmWasm, Starknet) are **not payable**,
  regardless of how severe a bug is. Several sessions of work went into those.
- Config-dependent and owner-dependent findings are **not payable** by rule.
- The bug has to be triggerable by an unprivileged attacker against a
  *currently deployed* EVM contract.

That rules out most of what was examined across this engagement and explains
why nothing payable surfaced: the areas that yielded findings were, by program
rule, the areas that cannot pay.

## Still worth reporting (just not for money)

The Starknet FastTokenRouter defects are real and will cost someone their
capital the day that feature is deployed. Out-of-scope for a bounty is not the
same as not worth reporting. Reasonable channels:

- A GitHub issue or PR on `hyperlane-xyz/hyperlane-starknet` (it is a public
  repo, and the fix is small and well-specified in the report).
- Hyperlane's Discord / security contact, as plain responsible disclosure with
  no bounty expectation.

Doing this costs nothing, requires no KYC, and is how a researcher builds
standing with a team.
