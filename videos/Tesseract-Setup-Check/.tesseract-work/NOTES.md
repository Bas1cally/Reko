# Setup check — notes

Intent: prove the Tesseract CLI installation renders a real motion graphic
end to end (fonts, keyframes, preview, filmstrip, H.264 export) in this
headless cloud container.

Current revision: r2 (`edits-v1.json` + JSON commit for font/layout + `edits-v2.json`).
`editable.json` is a fresh checkout of r2.

## Design
- 1920×1080, 3 s, silent. Dark ink background, amber rule, Archivo Black
  headline, IBM Plex Mono caption.
- Rule draws from the left (scaleX 0→100, 0–550 ms, ease-out); headline
  fades/rises 36 px (250–700 ms); caption follows (500–900 ms); hold to end.

## Checks performed
- `Previews/Filmstrip.png` from r2 at 0, 150, 300, 450, 600, 750, 900, 1500,
  2500, 2966 ms — sequence and layout as intended.
- `Setup-Check.mp4`: ffprobe = H.264 High, 1920×1080, yuv420p, 30 fps,
  90 frames, 3.000 s, no audio stream (project has no audio, by design).
- Decoded MP4 frames (`checks/mp4-decoded-frames.png`) match the filmstrip;
  per-frame luma (signalstats YAVG) rises monotonically 30.0→35.0 with no dips,
  so no black or flicker frames.

## Issues found
- `import-font` for IBMPlexMono-Medium.ttf returned
  `fontFamily: "IBM Plex Mono Medium"`, `fontStyle: "Regular"`, but rendering
  with that pair fails with `missing_fonts`. The typographic names
  (`"IBM Plex Mono"` / `"Medium"`) from the same face record resolve and render
  the correct face. Archivo Black (a single-style family) was unaffected.

## Environment used
- tsrct 0.2.0 (91214aa1), installed to ~/.local/share/Tesseract/bin/tsrct.
- Renderer: Mesa 25.2.8 llvmpipe (lavapipe) — CPU Vulkan, no GPU.
- Export: `--encoder-backend external-ffmpeg-command --ffmpeg-path /usr/bin/ffmpeg`
  (Ubuntu FFmpeg 6.1.1 with libx264 + AAC).
