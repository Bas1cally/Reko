# Method note — the door philosophy (from the Push Chain hunt)

A reframe for standing in front of a "perfect" contract. Keep this.

## The three ways past a locked door
- **b — kick the door / smash the window.** Attack the target's own guarded
  function head-on. This is the default and it *fails* against a hardened
  contract. If every function is "gated → closed", you are only doing b.
- **a — the spare key.** A second, forgotten path to the same privileged state:
  an alternate function, a default/uninitialized value, a deployment/init race,
  a proxy/storage layer *under* the door. Ask: is there another route to the
  state the front door protects?
- **c — the neighbour with the deposited key.** Confused-deputy / trust
  impersonation. Don't attack the target — attack *what the target trusts* and
  make it act for you, or spoof the identity the door waves through. Map the
  trust graph; find the trusted edge with the weakest, permissionlessly-reachable
  door.

## Reframes that actually opened new hunts
- **"Gated ≠ out of scope."** Critical usually allows *privilege escalation*:
  you don't need the key, you need to *become the keyholder*. Re-scan every
  permissionless state-write for whether its effect is later read by a
  privileged check. (Also check: uninitialized UUPS implementation →
  selfdestruct → brick; `_disableInitializers` on every upgradeable impl;
  clone-template init.)
- **Understand the door's *meaning*, not its weakness.** Why is it shut? Who
  shut it? What would have to *change* for it to open? If the only opener is a
  future commit / new config / v2 migration, that is a "noch nicht" — and most
  bounties rule "future/hypothetical deployments" out of scope. Don't submit it
  as "jetzt".
- **Patience = pick the right door, and watch this one.** When a target is
  genuinely, deliberately hardened (power pushed off-chain to trusted actors,
  thin permissionless surface), stop grinding it. Two moves: (1) *watch* it —
  re-audit each new commit / chain registration / migration, because that is
  where a correctly-set bolt gets reset wrong; (2) go hunt a house with *many*
  doors now.

## Target selection: fat permissionless surface > thin
Our paid wins all had fat permissionless surfaces the crook could actually reach:
Tare (vault fns + one-way `navStart`), Vesu (permissionless interest accrual),
Push SVM (permissionless `store_execute_ix_data` PDA squat). Push-Chain-Core
resisted a/b/c because it *deliberately* moved all power off-chain (UE-module,
Vault, TSS) — you can't confuse a deputy that lives off-chain. Prefer AMM /
lending / vault / **L1 protocol** code: many message handlers, ante paths,
precompiles → many doors, and (on an L1) a single crashing tx is already Critical.
