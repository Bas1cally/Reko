# Einreichung — Schritt für Schritt

> **Vorbehalt vorweg**: Ich habe in dieser Session keinen Internetzugang zu Sherlock. Der Ablauf
> unten ist der, wie ich ihn kenne — die Oberfläche kann sich geändert haben. Was ich sicher weiß,
> steht in Schritt 0 und ergibt sich direkt aus dem Template, das du geschickt hast. Wenn ein
> Menüpunkt anders heißt, halte dich an den Sinn, nicht an den Wortlaut.

---

## Schritt 0 — nichts committen

Das YAML, das du gepostet hast, ist **kein Ordner zum Hochladen**. Es ist die Definition eines
Formulars: `- type: textarea, id: summary, label: Summary` heißt „auf der Webseite gibt es ein Feld
namens Summary". Sherlock benutzt das GitHub-Issue-Form-Format nur als Beschreibungssprache.

Du reichst also ein, indem du **ein Webformular ausfüllst**. Kein Git, kein Commit, kein Upload,
kein Dateianhang. Alles wird als Text in Felder eingefügt — auch der PoC-Code.

## Schritt 1 — Zeilennummern besorgen (2 Minuten)

Zwei Stellen in `SUBMISSION.md` sind mit `<!-- LINE -->` markiert. Da gehören Links auf die echten
Codezeilen hin. In deinem Klon:

```bash
cd ~/2026-07-tare-DERFUEHRER21/tare-io__tare-contracts
grep -n "function updateNav" contracts/PortfolioVault.sol
grep -n "ownershipNonce\[from\]" contracts/LoansNFT.sol
```

Beide Befehle geben dir eine Zeilennummer. Daraus baust du die Links:

```
https://github.com/sherlock-audit/2026-07-tare-DERFUEHRER21/blob/main/tare-io__tare-contracts/contracts/PortfolioVault.sol#L<Nummer>
https://github.com/sherlock-audit/2026-07-tare-DERFUEHRER21/blob/main/tare-io__tare-contracts/contracts/LoansNFT.sol#L<Nummer>
```

Diese zwei Links ersetzen die `<!-- LINE -->`-Marker im Abschnitt **Root Cause**.

## Schritt 2 — auf die Contest-Seite

1. `audits.sherlock.xyz` öffnen, einloggen mit der Wallet, mit der du dich zum Contest angemeldet hast.
2. Den **Tare**-Contest suchen und öffnen.
3. Dort gibt es einen Bereich für Issues / Submissions. Der Knopf heißt sinngemäß **„Submit Issue"**.
4. Prüfe oben rechts, dass der Contest noch als **laufend** angezeigt wird.
   **Deadline: 29. Juli 2026, 17:00 UTC.** Danach ist das Formular zu, ohne Kulanz.

## Schritt 3 — Formular ausfüllen

Öffne `SUBMISSION.md` und kopiere Block für Block. Die Reihenfolge im Formular entspricht exakt der
Reihenfolge im Dokument.

| Feld im Formular | Was rein kommt | Pflicht |
|---|---|---|
| **Title** | die eine Zeile unter `## Title` | ja |
| **Summary** | der Absatz unter `## Summary` | ja |
| **Root Cause** | Abschnitt `## Root Cause` — **mit den Links aus Schritt 1** | ja |
| **Internal Pre-conditions** | die nummerierte Liste | ja |
| **External Pre-conditions** | `None.` plus der Erklärabsatz | ja |
| **Attack Path** | die nummerierte Liste 1–5 plus der Absatz danach | ja |
| **Impact** | Abschnitt `## Impact` inklusive Gas-Tabelle | ja |
| **PoC** | siehe Schritt 4 | optional, aber hier unbedingt |
| **Mitigation** | Abschnitt `## Mitigation` | optional, mach es trotzdem |

Markdown funktioniert in allen Feldern — Tabellen, Codeblöcke und Fettschrift kommen also richtig an.
Nichts umformatieren.

## Schritt 4 — der PoC

Ins PoC-Feld kommt:

1. Zuerst dieser Vorspann, **wörtlich** — er ist der Grund, warum der Judge dem Code traut:

   > Self-contained Foundry test. Only dependency is `forge-std`. 7 tests, all passing.
   >
   > `updateNav`, `_requireFreshNav`, `_requireIdleNav`, `_addLoanToNav`, `_removeLoanFromNav`,
   > `_invalidateNav` and the `LoansNFT._update` ownership-nonce block are copied **verbatim** from
   > the contest source — every branch, assignment and ordering unchanged. Roles, the ERC-20 and the
   > calculator arithmetic are reduced to stand-ins; the defect depends on none of them.
   >
   > `test_control_sweepCompletesWithoutInterference` is the no-attacker control.
   > `test_boundary_singleTransactionSweepIsImmune` demonstrates the precondition by showing the
   > attack failing against an atomic sweep.
   >
   > ```
   > forge init poc && cd poc
   > git clone --depth 1 https://github.com/foundry-rs/forge-std.git lib/forge-std
   > # paste the file below into test/NavFreeze.t.sol
   > forge test -vv
   > ```

2. Danach der **komplette Inhalt von `PoC-standalone.t.sol`** aus diesem Ordner, in einen
   Solidity-Codeblock (```solidity … ```).

Diese Datei ist genau dafür gebaut: eine einzige Datei, keine Imports außer `forge-std`, läuft sofort.
Ich habe sie isoliert getestet — 7 Tests, alle grün.

## Schritt 5 — abschicken

Nach dem Absenden ist die Submission privat sichtbar, bis der Contest endet. Dann kommt die
Judging-Phase mit Escalation-Fenster.

**Eine Einreichung, nicht mehrere.** Zerlege den Befund nicht in Einzelteile — Sherlock wertet
mehrere Issues zum selben Root Cause als Duplikate, und Spam schadet der Wertung.

---

## Wenn ein Judge nachhakt

Die drei wahrscheinlichsten Einwände und die kurze Antwort dazu:

**„Servicer/Originator ist trusted."** → Route A braucht überhaupt keine Rolle. Es reicht, *eine*
Loan-NFT zu besitzen und sie in den Vault zu schieben. Genau das zeigt
`test_routeA_plainTransferByAnyNftHolder`.

**„Das ist D-9 / Known Issue #16 / T-3."** → Die drei betreffen alle die **Korrektheit** des
NAV-Werts. Dieser Befund betrifft die **Terminierung** des Zyklus. D-9 beschreibt, was der Nonce
*nicht* erkennt; hier geht es darum, was er *erkennt* — und dass jedes Erkennen den kompletten
Fortschritt verwirft, beliebig oft erzwingbar.

**„Das Portfolio ist nie so groß."** → Gemessen: ab ~2.310 Krediten passt kein Sweep mehr in eine
10M-Gas-Transaktion. Und die Paginierung selbst (`batchSize`, `navCursor`, `pendingNav`,
`maxNavComputationTime`) ist die Aussage des Teams, dass Mehr-Batch-Betrieb der Normalfall ist —
sonst bräuchte es die ganze Maschinerie nicht.

Bleib bei den ehrlichen Einschränkungen, die im Text stehen (unbefristet statt unumkehrbar; Guardian
kann den Inhalt über `Rescuable` noch retten). Judges bestrafen Overclaiming härter als Zurückhaltung,
und ein Einwand, den du selbst schon beantwortet hast, kann dir nicht mehr vorgehalten werden.
