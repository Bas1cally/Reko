# 1inch solana-crosschain-protocol — first review pass

**Target**: `github.com/1inch/solana-crosschain-protocol` (in scope: whole repo,
Immunefi program `1inch-SmartContracts`, max $500k, launched June 2026)
**Scope status**: ✅ in scope — the repository itself is a `smart_contract`
asset, and the program has no "demonstrably unused" exclusion.
**Result of this pass**: **no exploitable fund-loss bug found.** Details below
so the next pass doesn't repeat the same ground.

## What the protocol does

Fusion+ style cross-chain atomic swap over two Anchor programs:

- `cross-chain-escrow-src` — maker locks tokens; resolvers fill (whole or
  partial, partial via a merkle tree of secrets); Dutch auction sets the
  destination amount.
- `cross-chain-escrow-dst` — resolver locks the counter-asset; the maker is
  `recipient`.
- `whitelist` — gates the "public" (third-party) actions.

Secret revealed on one side lets the counterparty claim on the other.

## Checked and sound

| Area | Finding |
|---|---|
| Timelock packing (`timelocks.rs`) | `U256` limb layout correct — `DEPLOYED_AT_MASK` really is bits 224..255; stage shifts stay inside the lower 224 bits |
| Withdraw vs cancel windows | Mutually exclusive on **both** programs: withdraw requires `now < Cancellation`, cancel requires `now >= Cancellation`. No ordering of stage deltas can make both true |
| Secret verification | `keccak(secret) == hashlock` on both src and dst |
| Account binding | `taker.key() == escrow.taker`, `creator.key() == escrow.creator`, `recipient.key() == escrow.recipient`; every ATA is constrained via `associated_token::authority`. Public withdraw cannot redirect funds |
| PDA derivation | Seeds consistent between `#[account]` constraints and the manual `seeds` arrays used for CPI signing |
| Whitelist gating | `public_withdraw`, `public_cancel_escrow`, `cancel_order_by_resolver` all require a `ResolverAccess` PDA from the whitelist program |
| Merkle proof | Sorted-pair hashing; leaf preimage is 40 bytes vs 64 for internal nodes, so no leaf/node collision. Root compared on bytes `[2..]` because `[0..2]` packs `parts_amount` — 30 bytes of root is still 240-bit security |
| Partial-fill index math | Internally consistent: on-chain formula, the test helper `get_index_for_escrow_amount`, and the `parts+1` leaf tree all agree |
| Arithmetic | `overflow-checks = true` in the release profile — the underflow/overflow paths I traced (`amount = 0` on first partial fill; `(order - remaining + amount - 1) * parts` for large orders) **panic and revert**, so they are DoS-shaped at worst, not silent wraparound |
| Auction (`calculate_rate_bump`) | No division by zero: a zero `time_delta` makes `timestamp <= next_point_time` false, so the branch is skipped and the loop invariant `current_point_time < timestamp` is preserved. Overflow bounded by u24 rate bumps |
| `get_dst_amount` / partial `dst_amount` | Ceiling division in both places — rounds in the maker's favour |
| `cancel_order_by_resolver` | `reward_limit` only ever lets the resolver take **less**; the premium is bounded by `max_cancellation_premium`, which `create` checks against the order ATA's lamports |

### Differential vs the EVM reference — checked, not a bug

`cross-chain-swap`'s `_isValidPartialFill` requires `calculatedIndex + 2` for a
complete fill and `+ 1` otherwise; the Rust version uses `+ 1` and `+ 0`.

That is a uniform re-basing (EVM 1-based, Solana 0-based), not an off-by-one:
the *relative* spacing is identical in both, and the Solana side is coherent
with its own tree (`parts + 1` leaves, complete fill consumes index
`parts_amount`). No overlap or reuse of a secret index is possible from this.

## Noted, not exploitable

- Two explicit `// TODO: Verify that safety_deposit is enough to cover
  public_withdraw and public_cancel methods` in both programs — an
  acknowledged, unfinished economic check. Not a theft path: an insufficient
  deposit only under-pays the third party who performs the public action.
- On the final fill, `amount_to_transfer` becomes the whole `order_ata.amount`,
  so tokens donated to the order ATA go to the last filler rather than the
  maker. Donations are voluntary; no victim.
- `create_escrow` has no `amount != 0` guard for partial fills; reaching it
  panics on the index arithmetic instead of being rejected cleanly.

## Not yet covered

- `1inch/solana-fusion` (separate in-scope repo, 7 source files)
- The `whitelist` program in depth (134 lines)
- `rescue_funds` on both programs, beyond the access-control check
- The EVM repos in the same program (`limit-order-protocol`,
  `fusion-protocol`, `cross-chain-swap`, `token-plugins`, `farming`,
  `delegating`)

## Assessment

The code is defensively written: constraints bind every account that matters,
the time windows cannot overlap, and arithmetic faults revert rather than
wrap. The classic Solana bug classes (missing signer/authority checks, PDA
substitution, unchecked ATAs, silent overflow) are all covered.

If a bug exists here it is more likely in cross-program economics — the
unfinished safety-deposit sizing, or an interaction between the auction and
partial fills — than in a single missing check.
