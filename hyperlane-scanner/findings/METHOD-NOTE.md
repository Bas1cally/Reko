# Method note — reachability before maths

Learned the hard way on the Kamino order-bonus finding: a wrong formula is not
a bug until an attacker can supply the input that triggers it.

That finding was fully proven at the maths level (unit test against production
types, 25% bonus vs a validated 10% cap) and still died, because
`get_liquidation_params` evaluates `check_liquidate_obligation` before the
order path and short-circuits on exactly the state the overshoot requires.

## The order of work, from now on

1. **Who can call this, and what do they control?** If the answer is "the
   owner" or "only in staging", stop — it is a hardening note at best.
2. **What state does the bug need, and can that state coexist with reaching
   the code?** Walk the control flow *backwards* from the buggy line to the
   instruction entry point. Short-circuiting `or_else`/early-return chains and
   feature flags are where candidate findings die.
3. **Only then** prove the maths.

## Where reachability is free

Prefer surfaces where an untrusted party is an intended actor, so step 2 is
satisfied by construction:

- permissionless liquidation
- oracle refresh / price ingestion
- flash loans
- anything a "public"/third-party instruction exposes

Prefer those over owner-configured features, where the attacker has to rely on
someone else's mistake.
