# `short.json` configuration

Paths are relative to the project directory.

## Root fields

```json
{
  "title": "Example Short",
  "canvas": [640, 360],
  "fps": 30,
  "duration": 15.0,
  "delivery_scale": 2,
  "background": "assets/background.png",
  "output": "output/short.mp4",
  "characters": {},
  "clips": [],
  "effects": [],
  "texts": [],
  "audio": {}
}
```

- `canvas`: logical pixel canvas.
- `delivery_scale`: integer nearest-neighbor upscale.
- `background`: exact-size background PNG.
- `output`: final H.264/AAC MP4 path.

## Characters and sequences

```json
"characters": {
  "hero": {
    "x": 170,
    "y": 260,
    "scale": 3,
    "default_sequence": "idle",
    "shadow": [22, 4],
    "sequences": {
      "idle": {
        "sheet": "assets/hero-idle.png",
        "frame_width": 40,
        "frame_height": 56,
        "frames": 6,
        "row": 2,
        "fps": 7,
        "flip_x": false
      }
    }
  }
}
```

The renderer trims transparent padding per cell. When a sheet is shorter than the requested row,
it automatically falls back to row zero for direction-neutral animation.

## Clips

```json
{
  "character": "hero",
  "sequence": "spin",
  "start": 5.2,
  "end": 8.4,
  "x0": 170,
  "y0": 260,
  "x1": 445,
  "y1": 155,
  "arc_height": 95,
  "rotation_turns": -1.0,
  "anchor": "center",
  "ease": "smooth",
  "frame_fps": 10,
  "hold_frame": null,
  "layer": 10
}
```

- Coordinates default to the character's base position.
- `arc_height` subtracts a sine arc from interpolated y.
- `rotation_turns` rotates over the clip; positive is counterclockwise in Pillow.
- `anchor`: `bottom` or `center`.
- `ease`: `linear`, `smooth`, or `out`.
- `hold_frame`: optional fixed zero-based cell.
- Later overlapping clips win for the same character.

## Effects

Impact:

```json
{
  "type": "impact",
  "time": 8.4,
  "duration": 0.35,
  "x": 450,
  "y": 150,
  "radius": 30,
  "shake": 6,
  "flash": 0.08
}
```

Dust or speed lines:

```json
{
  "type": "dust",
  "start": 4.5,
  "end": 5.4,
  "x0": 170,
  "y0": 263,
  "x1": 170,
  "y1": 263,
  "amount": 1.0
}
```

Use `"type": "speed_lines"` with the same timing/position fields.

## Text

```json
{
  "text": "FINISH.",
  "start": 12.8,
  "end": 15.0,
  "y": 276,
  "fade": 0.4,
  "color": [255, 241, 174],
  "shadow": [18, 22, 24]
}
```

## Audio

```json
"audio": {
  "chiptune": {
    "enabled": true,
    "gain": 0.035,
    "beat": 0.375,
    "notes": [164.81, 196.0, 246.94, 293.66]
  },
  "events": [
    {
      "type": "tone",
      "time": 5.2,
      "duration": 0.5,
      "f0": 180,
      "f1": 620,
      "gain": 0.13,
      "wave": "square"
    },
    {
      "type": "noise",
      "time": 8.4,
      "duration": 0.3,
      "gain": 0.35,
      "decay": 13,
      "seed": 22
    }
  ]
}
```

