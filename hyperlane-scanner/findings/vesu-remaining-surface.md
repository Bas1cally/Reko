# Vesu — what is left, and what is actually in scope

Written after the full pass over `vesu-v2`. Short version: the explicitly
in-scope code is finished, the genuinely soft part of the protocol is the
periphery, and **the periphery version that is actually running cannot be
reviewed** because its source is not published.

## The live deployment is bigger than the repo suggests

`vesu-v2/deployment.json` lists one pool. The pinned changelog
(`vesuxyz/changelog@3ed4dbe`, `deployments/deployment_sn_main_v2.json`) lists
the real set:

```
poolFactory  0x3760f903a37948f97302736f89ce30290e45f441559325026842b7a6fb388c0
oracle       0x00fe4bfb1b353ba51eb34dff963017f94af5a5cf8bdf3dfc191c504657f3c05
pools        6 addresses
multiply     0x7964760e90baa28841ec94714151e03fbc13321797e68a874e88f27c9d58513   <- periphery
liquidate    0x6b895ba904fb8f02ed0d74e343161de48e611e9e771be4cc2c997501dbfb418   <- periphery
migrate      0x2716dc8bf87005e2916241ac1167fb400cf69a708540c2c0c1672a654dbc5a9
```

Plus a still-listed v1.1 deployment (`singletonV2`, `extensionPOV2`, 12 pools,
its own `multiply` and `liquidate`).

## Scope, precisely

The Immunefi program lists exactly twelve assets:

- eleven `smart_contract` assets, each a file under `vesuxyz/vesu-v2/src/`
- `https://vesu.xyz`, type `smart_contract`, description **"Primacy of Impact"**

So the periphery, the migrate contract and everything v1.1 are **not listed
assets**. The only route to them is Primacy of Impact, which requires
demonstrating an actual impact on the live protocol — not just reading a defect
out of source.

## Status of each remaining component

### `vesuxyz/vesu-periphery` — the soft spot, and unreviewable

Leverage / looping / flash-liquidation: `multiply.cairo` (514),
`rebalance.cairo` (551), `multiply4626.cairo` (298), `liquidate.cairo` (283),
`swap.cairo` (193). This is the classic drain surface — it holds ERC20
allowances from every user of the "Multiply" feature and composes Ekubo swaps
with Vesu positions.

**All twelve branches target v1**: every one imports
`vesu::singleton::ISingletonDispatcher` and passes a `felt252 pool_id`. v2 has
no Singleton and no pool ids. Newest branch is 2025-07-31, still v1.

The `multiply` and `liquidate` contracts in the **v2** manifest are therefore
running code that exists in no public branch. It cannot be reviewed from source
here, and the deployed class cannot be fetched either: every Starknet RPC
(Alchemy, Blast, Nethermind, Lava) and both block explorers (Voyager,
Starkscan) are 403-blocked by this environment's egress policy.

What I did check, in the published v1 code, is whether the two standard
kill-shots are present. They are not:

| Attack | Result |
|---|---|
| Call `modify_lever` with `user = victim` to pull the victim's ERC20 allowance | closed — `multiply.cairo:510` `assert!(user == get_caller_address(), "caller-not-user")`, same guard at `multiply4626.cairo:294` |
| Call the Ekubo `locked()` callback directly with forged data to bypass that guard | closed — `consume_callback_data(core, data)` asserts the caller is Ekubo core, and core only calls back the address that invoked `lock()`, i.e. the contract itself |
| `liquidate.cairo` pulling repayment from a caller-supplied address | not applicable — it contains no `transferFrom` at all; it flash-borrows from Ekubo and sends only the residual to `recipient` |
| `rebalance.cairo` | owner-gated (`only-owner`) plus a `rebalancers` allowlist |

So the published periphery's authorization is correct. That says nothing
definitive about the unpublished v2 rewrite, but it does mean the obvious
pattern is one the team gets right.

### `vesuxyz/vesu-v1` — not an asset, likely wound down

The v2 manifest ships a `migrate` contract, which points at v1.1 being migrated
out. Reviewing it would repeat the mistake made earlier in this engagement with
`hyperlane-starknet`: real defects, zero payout, because the code was not an
asset.

### `vesu-v2` core — done

All eleven in-scope files reviewed; see `COVERAGE.md`. One finding, proven, in
`compute_liquidation_amounts`.

## Honest assessment of the core

The instinct that this protocol looks fragile is worth stating against, because
after a full read my view is the opposite for the in-scope code:

- Every arithmetic subtraction I traced is backed by an invariant that a
  `assert_*_config` function enforces at write time.
- Storage packing panics on overflow (`try_into().expect(...)`) instead of
  truncating, and `assert_storable_asset_config` does a full pack/unpack
  round-trip comparison on all twelve fields.
- Rounding is uniformly biased against the user — verified by fuzzing, not by
  eye (`property_tests.cairo`, five properties, all pass).
- Ownership transfer is two-step; the pausing agent can stop but not restart.
- The three previously-exploited bug classes (fee-share denominator, inflation
  fee reset, `receive_as_shares` rounding) are all genuinely fixed in v2, not
  papered over.

The one defect found is **economic, not a missing check**: the liquidation bonus
is not capped by the borrower's remaining equity, so past a certain LTV it is
paid out of lender principal. That is the kind of bug a careful reader finds and
a checklist does not.

## Concrete options, in order of expected value

1. **Submit the finding.** It is complete: proven against the real contract,
   reachability established from Vesu's own mainnet config, checked against all
   four disclosures. Nothing is blocking it.
2. **Ask Vesu for the v2 periphery source** — as part of the report thread, or
   via `security@vesu.xyz`. Programs routinely hand over unpublished source to a
   researcher who has already submitted something real. That converts the
   biggest remaining surface from unreviewable to reviewable.
3. **Run the analysis against mainnet from a machine with network access.** Two
   things are worth reading directly: `pair_config` on each of the six live
   pools (confirms the `liquidation_factor` values used here), and the deployed
   `multiply` class hash (lets you match or rule out the published branches).
4. Only then consider v1.1 — and only under Primacy of Impact, with a
   demonstrated impact rather than a source-level argument.
