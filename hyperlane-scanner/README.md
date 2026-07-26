# Hyperlane Bug-Bounty Scanner

A small triage tool for the [Hyperlane Immunefi bug bounty](https://immunefi.com/bug-bounty/hyperlane/)
(up to $2,500,000, smart contracts + blockchain + web app, KYC and PoC required
for high/critical). It does **not** find confirmed bugs — it clones the
Hyperlane monorepo, runs [Slither](https://github.com/crytic/slither) against
the in-scope contracts, and adds a small heuristic checklist for
Hyperlane-specific hot spots (message entry points, ISM signature checks,
delegatecall, etc.), then writes everything to one Markdown report you use as
a starting point for manual review.

## Prerequisites

- Python 3.9+
- [Foundry](https://getfoundry.sh) (`forge` on `PATH`)
- `pip install -r requirements.txt`

If `foundryup`/`binaries.soliditylang.org` are blocked by your network policy
(as in some sandboxed CI environments), install manually instead:

```bash
# forge binary straight from GitHub releases
curl -fsSL -o foundry.tar.gz \
  https://github.com/foundry-rs/foundry/releases/download/stable/foundry_stable_linux_amd64.tar.gz
mkdir -p ~/.foundry/bin && tar -xzf foundry.tar.gz -C ~/.foundry/bin
chmod +x ~/.foundry/bin/*
export PATH="$HOME/.foundry/bin:$PATH"

# solc 0.8.33 straight from GitHub releases, placed where svm/forge expects it
mkdir -p ~/.svm/0.8.33
curl -fsSL -o ~/.svm/0.8.33/solc-0.8.33 \
  https://github.com/ethereum/solidity/releases/download/v0.8.33/solc-static-linux
chmod +x ~/.svm/0.8.33/solc-0.8.33
```

## Usage

```bash
pip install -r requirements.txt
python3 scan.py
```

This clones `hyperlane-xyz/hyperlane-monorepo` into `./hyperlane-monorepo`
(reuse an existing checkout with `--skip-clone --repo-dir <path>`), builds the
`solidity` package with Foundry, runs Slither scoped to `contracts/` (tests,
scripts, mocks and third-party `dependencies/` are excluded — they're outside
Immunefi scope), and writes `reports/report.md`.

Useful flags:

| Flag | Purpose |
|---|---|
| `--repo-dir PATH` | Reuse an existing monorepo checkout |
| `--skip-clone` | Don't attempt to clone/update the repo |
| `--skip-deps` | Skip `forge soldeer install` |
| `--skip-build` | Reuse an existing Foundry `out/` |
| `--no-noise-filter` | Include noisy detectors (storage-gap shadowing, naming conventions, etc.) |
| `--out PATH` | Report output path (default `reports/report.md`) |

## What the report contains

1. **Slither findings**, grouped High → Optimization, restricted to Hyperlane's
   own `contracts/` (not OpenZeppelin/Chainlink/etc. dependencies, not tests).
2. **Manual-review checklist** — regex hits on patterns that are cheap to flag
   but need a human to judge: `process`/`handle`/`verify` entry points (check
   `onlyMailbox`/access control), `ecrecover`/`ECDSA.recover` (check replay and
   malleability), `delegatecall`, `selfdestruct`, unchecked low-level `.call`,
   and `unchecked { }` blocks.

## Next steps for any finding

Before submitting to Immunefi: reproduce with a concrete PoC (required for all
high/critical submissions), map the impact to the program's economic-damage
rules (critical/high on smart contracts are capped at 10% of the demonstrated
damage, subject to program-set minimums), and complete KYC (they require a
name and photo ID) before payout.
