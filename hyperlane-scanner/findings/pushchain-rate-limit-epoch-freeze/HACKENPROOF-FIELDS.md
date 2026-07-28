# HackenProof-Formular — Feld für Feld

Das Formular hat andere Felder als SUBMISSION.md. Hier passgenau aufgeteilt.
Titel steht schon. Es folgen: Feld 2 (Vulnerability details) und Feld 3 (Validation steps).
Ganz unten: Severity + die zwei Dateien anhängen.

═══════════════════════════════════════════════════════════════════════
## FELD 2 — "Vulnerability details" (was ist der Bug)
═══════════════════════════════════════════════════════════════════════

An unprivileged account can permanently lock the funds behind any large-payload outbound `execute` by
occupying and repeatedly closing its `StoredIxData` PDA. The finalize-by-reference route then never
finds its `ix_data`, and for any finalize transaction over Solana's 1232-byte limit the ref route is
the only route — so the execute can never complete and its bridged funds are permanently locked.

ROOT CAUSE

`store_execute_ix_data` (programs/universal-gateway/src/instructions/execute.rs) has no authorisation
of any kind — the caller is an unconstrained Signer, with no TSS signature, no config check and no
privileged role. Both PDA seeds (`sub_tx_id`, `ix_data_hash`) are supplied by the caller, and the
body validates only that `ix_data` is non-empty and hashes to `ix_data_hash`. It records the caller
as the slot owner:

    stored.store_refund_recipient = ctx.accounts.caller.key();

`close_stored_ix_data` then lets that same account close the slot at any time before finalize has
succeeded:

    if !executed_sub_tx_exists
        && ctx.accounts.caller.key() != ctx.accounts.store_refund_recipient.key()
    {
        return err!(GatewayError::StoredIxDataNotClosable);
    }

The account is closed with `close = store_refund_recipient`, so rent is refunded to the attacker on
every close. Occupying and vacating the slot is therefore free and unlimited.

`sub_tx_id` is not secret. INTEGRATION_GUIDE.md requires it to be deterministic and recommends
`keccak256(event_tx_hash || log_index)`, both derived from a public source-chain event; `ix_data` is
built from the same public fields. An attacker watching the source chain computes
`(sub_tx_id, ix_data_hash)` and acts before the relayer begins. This is pre-registration on public
data, not front-running.

WHY IT LOCKS FUNDS

docs/6-TX-SIZE-REF-ROUTE.md states the routing rule: a finalize transaction of 1232 bytes or less
uses direct `finalize_universal_tx`; above 1232 bytes it must use Store + `finalize_universal_tx_with_ix_data_ref`.
For a large-payload execute the ref route is the only route. The attacker selects such a transaction —
the ref route exists precisely because these are routine — and keeps its StoredIxData slot empty
whenever finalize would run.

Note the squat by itself is not the lock: `finalize_universal_tx_with_ix_data_ref` validates
`store_refund_recipient` against the stored value, so a relayer facing an occupied slot could finalize
by passing the attacker's address, losing only the 5,000-lamport upload fee. The lock is the CLOSE:
the attacker vacates the slot immediately before each finalize attempt, so the data is never present
when the ref route reads it.

IMPACT

Permanent lockout of end-user funds — the full value of any outbound execute the attacker targets,
with no upper bound. Permissionless, and the attacker's net cost across a multi-round campaign is
transaction fees only (measured 40,000 lamports over 4 cycles), because rent is refunded on every
close.

SUGGESTED FIX

Remove the revocation primitive. Smallest change: drop the pre-execution close branch and reclaim
rent only via the post-execution path (`executed_sub_tx_exists == true`), which is already
permissionless and already refunds the original storer. Once a slot is taken it then cannot be vacated
until the execute finalises, so squatting an intent gains nothing — the legitimate finalize consumes
the very data the attacker stored. Alternatively, require a valid TSS signature over
`(sub_tx_id, ix_data_hash)` in `store_execute_ix_data`.

═══════════════════════════════════════════════════════════════════════
## FELD 3 — "Validation steps" (wie reproduziert man es)
═══════════════════════════════════════════════════════════════════════

A runnable PoC is attached (poc.rs + Cargo.toml). It loads the REAL compiled program
(universal_gateway.so) into LiteSVM and dispatches every instruction to the on-chain code — nothing
is reimplemented.

Build and run:

  1. Build the program to BPF:
     cargo-build-sbf --manifest-path programs/universal-gateway/Cargo.toml
     (produces target/deploy/universal_gateway.so)
  2. Place the attached poc.rs and Cargo.toml in a cargo project whose relative path to
     universal_gateway.so matches the include in poc.rs (see the std::fs::read line), then:
     cargo run --release

Observed output:

  [1] attacker occupied the slot (no privileged role, no TSS signature)
  [2] relayer's own store of the same slot FAILED (init on a live account)
  [3] attacker closed the slot, refunded 9773800 lamports of rent
  [4.0] re-occupied and released again; slot empty
  [4.1] re-occupied and released again; slot empty
  [4.2] re-occupied and released again; slot empty
  >>> net attacker cost: 40000 lamports (tx fees only; rent recovered every cycle).
  ALL ASSERTIONS PASSED

Step by step, this shows:
  - Step 1: any keypair calls store_execute_ix_data and occupies the StoredIxData PDA for a chosen
    sub_tx_id — no privilege, no signature.
  - Step 2: the honest relayer's own store of the same slot reverts, because init hits a live account.
  - Step 3: the attacker calls close_stored_ix_data (permitted, since ExecutedSubTx does not exist yet
    and the attacker is the refund recipient) and recovers the full rent.
  - Step 4: the cycle repeats indefinitely. Closing immediately before each finalize attempt means the
    ref-finalize route never has its ix_data, so a large-payload execute can never be finalized.

Not a known issue: the README has no known-issues section, and the GitHub issue tracker (12 issues)
contains nothing about StoredIxData or the ref route. Not front-running: sub_tx_id and ix_data are
derived from a public source-chain event and are knowable before the relayer broadcasts.

═══════════════════════════════════════════════════════════════════════
## SEVERITY:  Critical
## ATTACH:    poc.rs  und  Cargo.toml  (aus dem poc/-Ordner)
═══════════════════════════════════════════════════════════════════════
