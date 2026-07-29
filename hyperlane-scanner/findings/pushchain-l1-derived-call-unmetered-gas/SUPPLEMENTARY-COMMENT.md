# Supplementary comment — post to the existing HackenProof report

Post-submission, we confirmed a second independent trigger for the same root
cause. Paste this as a comment on the report (do not resubmit — same file,
same fix, same bug):

---

Supplementary note: the same root cause (unmetered EVM gas on the
`res.Failed()` path of `DerivedEVMCallWithData` in
`push-chain-evm/x/vm/keeper/call_evm.go`) has a **second, independent,
permissionless, gasless trigger** beyond `MsgExecutePayload`:
`MsgMigrateUEA` (`x/uexecutor/keeper/msg_migrate_uea.go`) also routes through
the same derived-call primitive via `CallUEAMigrateUEA`
(`x/uexecutor/keeper/evm.go`), and is listed as gasless in
`app/txpolicy/gasless.go` alongside `MsgExecutePayload`. It is not
validator-gated. This broadens the reachable attack surface for the same
underlying accounting bug (two independent free entry points into the
unmetered-CPU path rather than one), which we wanted to flag for completeness
during triage. No new PoC is needed — the same fix (moving `ConsumeGas` above
the `res.Failed()` return in `call_evm.go`) resolves both entry points.
