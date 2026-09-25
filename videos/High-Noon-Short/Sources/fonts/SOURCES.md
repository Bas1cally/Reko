# Font sources

| File | Source | License |
| --- | --- | --- |
| `PixelifySans[wght].ttf` | https://github.com/google/fonts/tree/main/ofl/pixelifysans | SIL OFL 1.1 (`PixelifySans-OFL.txt`) |
| `PixelifySans-Bold.ttf` | static wght=700 instance of the file above (fontTools instancer); used in the project | SIL OFL 1.1 |
| `PressStart2P-Regular.ttf` | https://github.com/google/fonts/tree/main/ofl/pressstart2p | SIL OFL 1.1 (`PressStart2P-OFL.txt`) |

The static instance exists because Tesseract CLI 0.2.0 cannot reopen a project containing the variable file.
Both fonts are embedded in `High-Noon.tsrct`; the OFL permits redistribution.
