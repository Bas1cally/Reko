# PSVMSCDD-7 (StoredIxData squat-and-close) — adversarial re-scrutiny, 30 Jul 2026

Applied the same test-before-you-rely discipline that reshaped the two L1 findings,
verified against the real `execute.rs` @ the scope commit.

## The "permanent lockout" claim does NOT hold — it is a re-triggerable race the relayer wins

Verified from code (`instructions/execute.rs`):
- `store_execute_ix_data` (L183-199): permissionless; any `caller` becomes
  `store_refund_recipient`. When the slot is empty, the RELAYER can store it and own it.
- `close_stored_ix_data` (L239-242): closable only if
  `executed_sub_tx_exists || caller == store_refund_recipient`. Once the relayer owns
  the slot, the attacker (caller != owner) CANNOT close it → relayer finalizes → done.
- The PDA seed includes `ix_data_hash` and store enforces `keccak(ix_data)==ix_data_hash`
  (L191-192), so the attacker cannot place unusable data at the correct address — only the
  correct public ix_data. Occupied-with-correct-data ⇒ the relayer can finalize using it.

The contradiction that defeats the attack: the attacker cannot keep the slot
simultaneously OCCUPIED (to block the relayer's store) and EMPTY (to block finalize).
- Occupied → relayer finalizes with the stored (correct) data.
- Empty (the close needed to block finalize) → relayer stores it and becomes owner →
  attacker can no longer close → finalize succeeds permanently.
Every close (required to block a finalize) opens exactly the store-race window the relayer
needs. The attacker must win every race forever; the relayer needs to win once. Tried the
atomic close+store line for the attacker — still contradictory (always-occupied ⇒ finalize
works). No attacker line yields a permanent lock.

## Consequences (same failure class as Tare and the #442 downgrade)
1. NOT permanent — recovery exists (relayer stores the empty slot once). At most
   re-triggerable griefing.
2. Front-running-dependent — the close must front-run each finalize tx; commonly excluded.
3. PoC gap — `poc.rs` proves the cheap permissionless store/close primitive and rent
   recovery, but NOT the end-to-end "relayer can never finalize" against a determined
   relayer winning the store-race with priority fees.

## Honest severity
Griefing / temporary finalize-DoS via priority-fee races — Medium-ish, contestable, and
front-running-flavored. NOT a clean permanent-lockout Critical.

## Recommendation
Same as #442: do not let it stand as an unqualified Critical. Either (a) build a PoC that
actually demonstrates the attacker winning the store-race against a relayer that tries to
store-to-own (I believe this fails), or (b) post an honest scoping correction / withdraw.
Protects the credibility of #440 (the solid gas-metering Critical).

## Validation: the ALT / "alternative route" bypass — CHECKED and REJECTED

Considered whether Solana Address Lookup Tables (v0 txs) let the relayer route
around the squat by shrinking the finalize tx under 1232 bytes (so the direct
`finalize_universal_tx` fits, no PDA needed). Verified against execute.rs:
`ix_data` is a `Vec<u8>` passed as INSTRUCTION DATA (L187, L256), and the ref
path enforces `require!(ix_data.is_empty())` (L446) precisely to keep large
ix_data OUT of the transaction. ALTs compress ACCOUNTS, not instruction bytes,
so for a genuinely large `ix_data` payload they do not help — the ref route IS
the only route, exactly as the finding claims. This bypass is INVALID; the
finding is correct on the "only route" point. The sole valid reason the finding
is weak is the store-race argument above (relayer stores the empty slot, becomes
owner, attacker can no longer close, finalize succeeds).
