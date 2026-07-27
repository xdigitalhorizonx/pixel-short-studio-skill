# Pixel-short production pipeline

## 1. Establish the style contract

Inspect original-size reference images. Record:

- Native logical canvas and delivery aspect ratio.
- Effective sprite pixel size and expected character height.
- Palette size, hue bias, shading-band count, and outline colors.
- Perspective, ground plane, anchor convention, and draw order.
- Background detail density versus character silhouette density.
- Lighting that is baked into art versus effects drawn at runtime.
- UI/text treatment and whether small fonts are bitmap or canvas-drawn.
- Explicit avoid list: smoothing, gradients, glows, extra outlines, camera blur, or palette drift.

Create a side-by-side style board or contact sheet when multiple source assets exist.

## 2. Turn prose into timed beats

A short needs a legible action sentence. Use this sequence:

1. Establish location and facing.
2. Anticipate the action.
3. Launch or initiate.
4. Escalate with travel or rotation.
5. Hold contact for 2–8 logical frames.
6. Show the target's reaction.
7. Recover or land.
8. End on a stable readable pose.

Write exact start/end seconds and planned sprite sequence for every beat. Allocate more time to
anticipation and aftermath than the literal contact frame.

## 3. Choose an asset path

### Existing or licensed sprites

Prefer these when animation completeness and identity consistency matter. Preserve source files,
license terms, and credits. Confirm the sheet layout: rows, columns, frame cell size, transparent
background, direction order, and non-directional sheets.

### Generated pose strips

Generate all poses for one action in one image. Supply the strongest style references as inputs.
Use a flat key color that does not occur in the character. Require:

- One row or a precisely defined grid.
- Consistent character scale, palette, lighting, and proportions.
- Generous separation and no cropped extremities.
- No labels, borders, shadows, floor, or effects.

Inspect the output before chroma removal. Segment by alpha-density valleys or known cells. Do not
independently prompt every frame.

### Blender pre-render

Use when a scene needs repeatable 3D camera blocking or a rig already exists. Render to the native
logical grid with orthographic or locked perspective, disable smoothing, quantize deliberately,
and export transparent sprite passes separately from backgrounds.

## 4. Compose deterministically

Use the bundled renderer for ordinary 2D shorts. Configure character sequences and timed clips in
`short.json`. Prefer bottom-center anchors for grounded poses and center anchors for airborne
rotation. Drive the action with explicit keyframes, arc height, and rotation—not inferred motion.

Layer effects at logical resolution:

- Blob shadow.
- Dust or launch debris.
- Speed lines.
- Palette-bound impact star.
- Short white flash.
- Decaying integer camera shake.
- Sparse pixel text.

Upscale only at encode time with nearest-neighbor filtering.

## 5. Add cleared audio

The renderer can synthesize square-wave music, tones, and noise bursts. For external audio, record
its source and usage rights. Separate sound roles:

- Anticipation cue.
- Launch/whoosh.
- Contact crack plus low-frequency body.
- Landing grit.
- Resolve sting.

## 6. Validate and iterate

Create previews at decisive moments and a timeline contact sheet. Look for missing frames, wrong
sprite rows, anchor jumps, scale changes, cropped silhouettes, unreadable contact, and reaction
timing. Then run the validator and record duration, fps, frame count, codecs, resolution, and audio.

