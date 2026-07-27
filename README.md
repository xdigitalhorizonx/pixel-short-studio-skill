# Pixel Short Studio

A skill that turns a script into a reproducible, verified 15–30 second pixel-art short.

Most "AI animation" stops at a prompt and a plausible-looking clip. This one is built around a
paper trail: a style contract written *before* any art exists, a shot chart with exact time ranges,
a deterministic compositor driven by a single JSON file, and a validation pass that probes the
delivered MP4 and renders a contact sheet you actually have to look at. Re-running the renderer on
the same `short.json` produces the same frames.

## Pipeline

```
script → style-contract.md → shot-chart.md → assets → short.json → render → validate → deliver
```

| Stage | Artifact | Enforces |
|---|---|---|
| Style contract | `style-contract.md` | Resolution, palette, outlines, anchors, lighting, forbidden drift |
| Shot chart | `shot-chart.md` | Exact time ranges per beat: establish → anticipation → action → contact → reaction → recovery → resolve |
| Config | `short.json` | Characters, sprite sequences, clips, effects, text, procedural audio |
| Render | `output/short.mp4` | Deterministic Pillow/NumPy compositing, FFmpeg encode |
| Validate | contact sheet + probe | Real delivery specs, real frames — not "the file exists" |

## Requirements

- Python 3 with `numpy` and `Pillow`
- `ffmpeg` and `ffprobe` on `PATH`

## Quickstart

```bash
python skills/pixel-short-studio/scripts/init_project.py --name my-short --out ./projects
```

Write `style-contract.md` and `shot-chart.md`, build assets, author `short.json`
(see [`references/config-schema.md`](skills/pixel-short-studio/references/config-schema.md)), then:

```bash
python skills/pixel-short-studio/scripts/render_pixel_short.py --project ./projects/my-short
```

```bash
python skills/pixel-short-studio/scripts/validate_video.py ./projects/my-short/output/short.mp4
```

`validate_video.py` defaults to 30 fps and a 15–30 s duration window; override with `--expect-fps`,
`--min-duration`, `--max-duration`, and `--contact-sheet`.

## Defaults

640×360 logical canvas · 30 fps · 2× nearest-neighbor → 1280×720 delivery. Bottom-center anchors for
grounded sprites, center anchors for rotations. Effects are palette-bound, hard-edged, and snapped to
logical pixels. Override only when the supplied style defines another native grid.

## Layout

```
.codex-plugin/plugin.json            Plugin manifest
skills/pixel-short-studio/
├── SKILL.md                         Workflow and production rules
├── agents/openai.yaml               Agent interface
├── assets/project-template/         Neutral starter project — no third-party art
├── references/
│   ├── pipeline.md                  Asset and animation production decisions
│   ├── config-schema.md             short.json contract
│   └── qa.md                        Visual and technical acceptance checks
├── scripts/
│   ├── init_project.py              Copy the starter project
│   ├── render_pixel_short.py        Render frames + procedural audio → MP4
│   └── validate_video.py            Probe delivery specs, build contact sheet
└── team-kill-quota/                 Worked example (see below)
```

## The worked example

`team-kill-quota/` is a real short produced with this skill — a reference for how a finished project
is actually structured. Tracked here: `render_short.py`, `prepare_assets.py`, `short.json`, the shot
chart, the style contract, and the full sprite set under `assets/` — four operators with 4-frame walk
cycles, a fall sequence, an aim pose, and the forest background.

The sprites are the useful part to study: 32-ish-pixel figures that read entirely through silhouette
and timing, bottom-center anchored, with no anti-aliasing on any edge.

Not tracked: `output/` renders, `frames/` QA captures, and `source/` raw generations. `source/audio/`
holds two third-party music files, so `render_short.py` will not run end-to-end from a clean clone —
it resolves `MUSIC_SOURCE` and `DISCORD_LEAVE_SOURCE` under `source/audio/`. Supply your own cleared
audio and repoint those constants.

That gap is deliberate, and it is the rule the skill enforces: record every non-original source asset
in `ATTRIBUTION.md`, and add original or cleared audio rather than silently reusing music from a
reference project.

## License

MIT — see [LICENSE](LICENSE). The license covers this skill's code and documentation only, not any
third-party or franchise material you bring into a project built with it.
