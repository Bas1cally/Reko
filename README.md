# Sprites: Bilder und Clips

Arbeits-Repo für Figuren-Sprites (BoF3-Projekt): Standbilder, Clips und fertige Sprite-Sheets in
8 isometrischen Richtungen (walk, run, idle, attack). Die bezahlten Schritte laufen über die
**Venice.ai-API**, alles andere lokal und kostenlos.

## Aufbau

| Ordner / Datei                        | Inhalt                                                                  |
| ------------------------------------- | ----------------------------------------------------------------------- |
| `.claude/skills/scenario-iso-cycles/` | Der Skill: Ablauf, Prompt-Rezepte, Lehren, lokale Skripte               |
| `tools/venice.py`                     | Venice-Client: Modelle, Preise, Standbilder, Ansichten, Clips           |
| `raw/`                                | Standbilder und erste Frames (960×960, Magenta-Hintergrund)             |
| `clips/`                              | Generierte Clips `<held>_<richtung>_<zyklus>.mp4`                       |
| `sprites/`                            | Fertige Sheets `<held>_<zyklus>.png` + `meta.json` + Vorschau-GIFs      |
| `qa/`                                 | 8-Richtungs-Vorschauen und Kontaktbögen zur Abnahme                     |
| `cast.json`, `prompts.json`, `jobs.json` | Figuren, erzeugte Aufträge, laufende Video-Jobs                      |

## API-Schlüssel

Cloud-Sitzung: als Network Secret (Bearer) für `api.venice.ai` hinterlegen, der Proxy setzt den Header. Lokal: `cp .env.example .env` und `VENICE_API_KEY=...` eintragen.
`.env` ist in `.gitignore`: der Schlüssel kommt nie ins Repo.

## Kurzablauf

```bash
S=.claude/skills/scenario-iso-cycles/scripts
python3 tools/venice.py models video --grep kling            # Modelle ansehen (ohne Schlüssel)
python3 $S/make_prompts.py cast.json --still-model gpt-image-2-5-sunburst --clip-model minimax-h3-max-turbo-image-to-video
python3 tools/venice.py quote prompts.json                   # Preis, nichts wird ausgegeben
python3 tools/venice.py stills prompts.json --ids held_still # Standbild, 2 Varianten nach raw/
python3 $S/reframe.py held raw/held_still_1.png --facings se,ne --out raw
# Pfade in cast.json unter "stills" eintragen, make_prompts.py --force, Ansichten, dann:
python3 tools/venice.py clips prompts.json --ids held_se_walk,held_se_run
python3 tools/venice.py wait                                  # lädt nach clips/
python3 $S/process.py cast.json held --clips clips --out sprites --report
```

Details: `.claude/skills/scenario-iso-cycles/SKILL.md` und `references/venice.md`.
