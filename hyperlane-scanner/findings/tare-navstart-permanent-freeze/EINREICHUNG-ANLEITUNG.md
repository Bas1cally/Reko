# Einreichung — Schritt für Schritt

> **Korrektur einer früheren Version dieser Datei.** Ich hatte hier geschrieben, es werde über ein
> Webformular auf `audits.sherlock.xyz` eingereicht und man solle nichts committen. Das war falsch.
> Das Contest-README sagt wörtlich:
>
> > *"Submit findings using the **Issues** page in your private contest repo (label issues as
> > **Medium** or **High**)"*
>
> Es sind **GitHub-Issues** in deinem privaten Contest-Repo. Genau deshalb existiert das YAML-Template
> überhaupt: GitHub rendert daraus das Formular für „New issue". Der Rest der alten Anleitung
> (Feldzuordnung, PoC-Format) stimmt weiterhin — nur der Ort war falsch.

---

## Schritt 1 — die zwei Permalinks besorgen (2 Minuten)

Zwei Stellen in `SUBMISSION.md` sind mit `<!-- LINE -->` markiert. Der bequemste, fehlerfreie Weg:

1. Öffne in deinem Contest-Repo die Datei:
   `https://github.com/sherlock-audit/2026-07-tare-DERFUEHRER21/blob/main/tare-io__tare-contracts/contracts/PortfolioVault.sol`
2. Suche mit der Browsersuche nach `function updateNav`.
3. Klick auf die **Zeilennummer** links davon, dann drück **`y`** — GitHub wandelt die URL in einen
   Permalink mit Commit-Hash um. Adresszeile kopieren.
4. Dasselbe für `LoansNFT.sol`, Suchbegriff `ownershipNonce[from]`.

Alternativ, falls du lieber auf das kanonische Scope-Repo verlinkst (Commit steht im README):

```text
https://github.com/sherlock-scoping/tare-io__tare-contracts/blob/b215321b218aac7e7fc0072d97c74e93f23bdaf7/contracts/PortfolioVault.sol#L<Nummer>
https://github.com/sherlock-scoping/tare-io__tare-contracts/blob/b215321b218aac7e7fc0072d97c74e93f23bdaf7/contracts/LoansNFT.sol#L<Nummer>
```

Zeilennummern lokal holen:

```bash
cd ~/2026-07-tare-DERFUEHRER21/tare-io__tare-contracts
grep -n "function updateNav" contracts/PortfolioVault.sol
grep -n "ownershipNonce\[from\]" contracts/LoansNFT.sol
```

Nimm im Zweifel Variante 1 — dein eigenes Repo existiert garantiert, das Scoping-Repo konnte ich von
hier aus nicht aufrufen.

## Schritt 2 — Issue anlegen

1. `https://github.com/sherlock-audit/2026-07-tare-DERFUEHRER21/issues`
2. **New issue**
3. Falls eine Template-Auswahl erscheint: **Audit Item** wählen. Dann sind die Felder schon da.
   Erscheint keine Auswahl, ist es ein freies Textfeld — dann schreib die Überschriften
   (`## Summary`, `## Root Cause`, …) selbst, in genau der Reihenfolge aus `SUBMISSION.md`.

## Schritt 3 — Felder ausfüllen

`SUBMISSION.md` aufmachen, Block für Block kopieren. Die Reihenfolge im Dokument ist exakt die
Reihenfolge im Formular.

| Feld | Was rein kommt |
|---|---|
| **Title** | die Zeile unter `## Title` |
| **Summary** | der Absatz unter `## Summary` |
| **Root Cause** | Abschnitt `## Root Cause` — **mit den Permalinks aus Schritt 1** |
| **Internal Pre-conditions** | die nummerierte Liste |
| **External Pre-conditions** | `None.` plus Erklärabsatz |
| **Attack Path** | Liste 1–5 plus den Absatz danach |
| **Impact** | Abschnitt `## Impact` inklusive Gas-Tabelle |
| **PoC** | siehe Schritt 4 |
| **Mitigation** | Abschnitt `## Mitigation` |

Markdown funktioniert überall — Tabellen, Codeblöcke, Fettschrift kommen richtig an. Nichts
umformatieren.

## Schritt 4 — der PoC

Erst dieser Vorspann, **wörtlich**:

> Self-contained Foundry test. Only dependency is `forge-std`. 7 tests, all passing.
>
> `updateNav`, `_requireFreshNav`, `_requireIdleNav`, `_addLoanToNav`, `_removeLoanFromNav`,
> `_invalidateNav` and the `LoansNFT._update` ownership-nonce block are copied **verbatim** from the
> contest source — every branch, assignment and ordering unchanged. Roles, the ERC-20 and the
> calculator arithmetic are reduced to stand-ins; the defect depends on none of them.
>
> `test_control_sweepCompletesWithoutInterference` is the no-attacker control.
> `test_boundary_singleTransactionSweepIsImmune` demonstrates the precondition by showing the attack
> failing against an atomic sweep.
>
> ```bash
> forge init poc && cd poc
> git clone --depth 1 https://github.com/foundry-rs/forge-std.git lib/forge-std
> # paste the file below into test/NavFreeze.t.sol
> forge test -vv
> ```

Danach der komplette Inhalt von **`PoC-standalone.t.sol`** in einen ```solidity-Codeblock.

## Schritt 5 — Label setzen

Rechts in der Seitenleiste ein Label vergeben: **High**.

Das README verlangt ausdrücklich ein Label (`Medium` oder `High`) — ohne Label kann das Issue
aussortiert werden. Setz **High**. Ein Judge stuft bei Bedarf herunter; ein zu niedrig gelabeltes
Issue wird selten hochgestuft.

## Schritt 6 — absenden

**Deadline: 29. Juli 2026, 17:00 UTC.**

Beachte: der Contest läuft mit **Live Issues** — dein Issue geht sofort an das Protokoll-Team. Umso
wichtiger, dass es beim ersten Mal sitzt. Nicht in mehrere Issues zerlegen; ein Root Cause, ein Issue.

---

## Wenn ein Judge nachhakt

**„Servicer/Originator ist trusted."** → Route A braucht überhaupt keine Rolle. Und das Q&A sagt
selbst: *"The Investor is identified by loan-NFT ownership which can potentially be untrusted."*
Genau der Fall. Siehe `test_routeA_plainTransferByAnyNftHolder`.

**„Array-Längen-DoS ist out of scope."** → Das Q&A schließt aus: *"Any resulting gas/DoS exposure
requires a **trusted role** to supply an oversized array."* Hier liefert niemand ein übergroßes Array.
Die Liste wächst durch normalen Betrieb; ausgelöst wird der Freeze von einem **untrusted** Aufrufer.
Und derselbe Absatz schließt es positiv ein: *"Any value or array-length input reachable by an
untrusted party (Borrower, Investor, or an arbitrary caller) that is not adequately bounded **is in
scope**."*

**„Das ist D-9 / #16 / T-3."** → Die drei betreffen die **Korrektheit** des NAV-Werts. Dieser Befund
betrifft die **Terminierung** des Zyklus. D-9 beschreibt, was der Nonce *nicht* erkennt; hier geht es
darum, was er *erkennt* — und dass jedes Erkennen den gesamten Fortschritt verwirft, beliebig oft
erzwingbar.

**„So große Portfolios gibt es nicht."** → Gemessen: ab ~2.310 Krediten passt kein Sweep mehr in eine
10M-Gas-Transaktion, und das Deployment ist **Avalanche C-Chain**, wo das Block-Gaslimit deutlich
unter Ethereums 30M liegt — die Schwelle sinkt also weiter. Dazu ist die Paginierung selbst
(`batchSize`, `navCursor`, `pendingNav`, `maxNavComputationTime`) die Aussage des Teams, dass
Mehr-Batch-Betrieb der Normalfall ist.

Bleib bei den ehrlichen Einschränkungen im Text. Judges bestrafen Overclaiming härter als
Zurückhaltung, und ein Einwand, den du selbst schon beantwortet hast, kann dir nicht mehr
vorgehalten werden.
