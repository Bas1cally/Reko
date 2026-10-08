# Session log

Wie der Skill es verlangt: Modelle, Jobs, Preise, Fehler mit Grund und Lösung. Damit setzt die
nächste Sitzung nahtlos fort.

## 2026-10-08: Figur `gunner`

**Vorlage:** `ref/gunner_turnaround.jpg` (4 Ansichten, Augenhöhe, flaches Grau 205), dazu die
Detailbilder der Kanone. HD, 128 px, alle 8 Richtungen generiert (die Kanone liegt auf der rechten
Schulter).

**Modelle**
- Ansichten: `gpt-image-2-5-flare-edit` (0,08 $) für SE, NE, S, N, SW, NW; `nano-banana-2-1-edit`
  (0,10 $) für E. `gpt-image-2-5-sunburst-edit` und `flux-3-image-edit` lieferten am 8.10. nur
  HTTP 502 (Upstream).
- Clips: `minimax-h3-max-turbo-image-to-video` (0,14 $ / 5 s, 768P). Tests gegen `flux-3-*`
  (0,94 $) und `wan-3-0-image-to-video` (0,33 $ bei 480p), siehe unten.

**Erste Frames** (`raw/gunner_<richtung>_still.png`): SE `se_turnaround_1`, NE `ne_turnaround_1`,
S/N/SW/NW jeweils `_turnaround_1`, E `e_turnaround_2` (Nano, steile Kanone). W ist E gespiegelt.
Verworfenes liegt in `raw/rejected/`.

**Test der Videomodelle** (SE gehen, NE rennen, SE Angriff), ausgewertet mit `process.py --report`:

| Modell | Seam gehen | Seam rennen | Angriff |
|---|---|---|---|
| MiniMax Turbo | 0,25 | 0,08 | Kanone senkrecht, schießt seitlich, Rauch |
| Flux 3 | 3,86 (kein Zyklus) | 0,31 | dasselbe |
| Wan 3.0 | 0,28 | Anbieterfehler, erstattet | beidhändig, Gatling |

Messung Endbild: bei allen drei Modellen landet der letzte Frame auf dem Startbild, wenn
`end_image_url` gesetzt ist (Wan pixelgenau). Ohne Endbild weicht er ab.

**Fehler, Grund, Lösung**
1. Kanone vor dem Gesicht in E/W. Grund: Wer am hinteren Griff auf Schulterhöhe hält, hat die Hand
   im Profil vor dem Gesicht (auch in der Vorlage). Lösung: E mit steiler Kanone, Hand auf Brusthöhe.
2. Kein Bildmodell zeichnete W (Profil links, Kanone auf der hinteren Schulter). Notlösung: W =
   gespiegeltes E (Kanone dort links). Offen: W neu, wenn es stört.
3. Videomodelle nach ganzen Clips beurteilt statt nach den Loops. Grund: Schritt `process.py
   --report` übersprungen. Lösung: immer erst den Report und die Loop-GIFs ansehen.
4. Angriff bei allen Modellen falsch. Grund: Ziel nicht pro Richtung beschrieben, Rauch im Prompt,
   „3D render“ in der Negativliste gegen den eigenen Stil. Lösung: `attack_facing` für alle 8
   Richtungen, kein Rauch, pro Figur `negative` und `negative_attack`, „3D render“ fällt bei HD weg.
5. Modelle gewechselt, ohne neu zu bepreisen: 10,40 $ statt der angesagten ~6 $. Lösung: vor
   jedem neuen Modell `quote` und Okay einholen.

**Guthaben:** 42,29 → 31,92 Bundled Credits.
