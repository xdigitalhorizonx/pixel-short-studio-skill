---
name: pixel-short-studio
description: Create reproducible 15–30 second pixel-art videos from scripts, shot charts, game-art references, sprite sheets, or animation briefs. Use when Codex must inspect an existing pixel style, plan beats and camera action, generate or integrate consistent sprite animation, render a short-form MP4 with hard-edged effects and audio, validate the timeline visually and technically, or establish a reusable script-to-pixel-short production pipeline.
---

# Pixel Short Studio

Translate a script into an evidence-backed style contract, shot chart, assets, deterministic
compositor, verified MP4, and reproducible project folder.

## Workflow

1. Inspect the supplied folder and treat its assets, exact paths, screenshots, and corrected names
   as authoritative. Do not claim a style match from prose alone.
2. Read [references/pipeline.md](references/pipeline.md). Read
   [references/config-schema.md](references/config-schema.md) before authoring `short.json`.
3. Initialize an isolated project:

   ```powershell
   python scripts/init_project.py --name <slug> --out <parent-directory>
   ```

4. Write `style-contract.md` before creating art. Record logical resolution, pixel density,
   palette/shading, outline treatment, anchors, camera, lighting, effects, and forbidden drift.
5. Convert the script into `shot-chart.md` with exact time ranges. Keep the action readable in
   held key poses: establish, anticipation, action, contact/hit-stop, reaction, recovery, resolve.
6. Build assets:
   - Reuse provided or properly licensed assets when they satisfy the style contract.
   - For generated animation, create a complete pose strip in one generation. Never generate
     adjacent frames independently; identity and proportions drift.
   - Keep sources and attribution under `source/`. Do not bundle third-party or franchise artwork
     into a shareable/commercial template without permission.
   - Use nearest-neighbor scaling and hard pixel-grid effects. Do not smooth final sprites.
7. Author `short.json`, then render:

   ```powershell
   python scripts/render_pixel_short.py --project <project-directory>
   ```

8. Read [references/qa.md](references/qa.md), inspect every generated preview and the contact sheet,
   then validate:

   ```powershell
   python scripts/validate_video.py <project-directory>/output/short.mp4
   ```

9. Iterate on the weakest visible beat. Re-render the full timeline after any timing, crop, anchor,
   or sprite-sheet-row change.
10. Deliver the MP4, `short.json`, shot chart, style contract, source/attribution notes, renderer
    command, validation results, and contact sheet.

## Production rules

- Default to a 640×360 logical canvas, 30 fps, and 2× nearest-neighbor 1280×720 delivery unless
  the supplied style defines another native grid.
- Maintain bottom-center anchors for grounded sprites and center anchors for rotations.
- Animate travel and sprite phase from measurable time or distance; avoid accidental skating.
- Use anticipation, short hit-stop, reaction displacement, and recovery instead of excessive
  tweening. Pixel animation reads through silhouettes and timing.
- Keep effects palette-bound, hard-edged, and aligned to logical pixels.
- Add original or cleared audio. Do not silently reuse copyrighted music from a reference project.
- Review actual rendered frames. File existence and successful encoding are not visual QA.
- Keep work isolated from the source game unless the user explicitly requests integration.

## Tool selection

- Use an image-generation skill when new raster art is required. Supply real style-reference images
  and request one complete pose strip on a removable flat key color.
- Use Blender only when the chosen pipeline genuinely needs 3D blocking, camera work, or
  pre-rendered sprite passes. The compositor does not require Blender.
- Use FFmpeg for encoding and probing. Use Pillow/NumPy for deterministic pixel compositing,
  sprite extraction, and procedural audio.
- If generation is blocked or inconsistent, pivot to user-supplied, licensed, or hand-edited
  sprites and record the source. Do not hide the pivot.

## Bundled resources

- `scripts/init_project.py`: copy the neutral starter project.
- `scripts/render_pixel_short.py`: render a config-driven pixel short and procedural audio.
- `scripts/validate_video.py`: probe delivery specs and create a timeline contact sheet.
- `assets/project-template/`: neutral project skeleton; contains no third-party art.
- `references/pipeline.md`: asset and animation production decisions.
- `references/config-schema.md`: renderer configuration contract.
- `references/qa.md`: visual and technical acceptance checks.
