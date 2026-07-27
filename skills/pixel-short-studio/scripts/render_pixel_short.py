#!/usr/bin/env python3
"""Render a config-driven pixel short from <project>/short.json."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def interpolation(t: float, mode: str) -> float:
    t = clamp(t)
    if mode == "smooth":
        return t * t * (3 - 2 * t)
    if mode == "out":
        return 1 - (1 - t) ** 3
    return t


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def load_sequences(project: Path, characters: dict) -> dict:
    loaded = {}
    for char_name, char in characters.items():
        sequences = {}
        for seq_name, spec in char["sequences"].items():
            sheet = Image.open(project / spec["sheet"]).convert("RGBA")
            fw, fh = int(spec["frame_width"]), int(spec["frame_height"])
            row = int(spec.get("row", 0))
            row = row if sheet.height >= (row + 1) * fh else 0
            frames = []
            for index in range(int(spec["frames"])):
                cell = sheet.crop((index * fw, row * fh, (index + 1) * fw, (row + 1) * fh))
                bbox = cell.getbbox()
                if bbox:
                    cell = cell.crop(bbox)
                if spec.get("flip_x"):
                    cell = cell.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                scale = int(char.get("scale", 1))
                cell = cell.resize((cell.width * scale, cell.height * scale), Image.Resampling.NEAREST)
                frames.append(cell)
            sequences[seq_name] = {
                "frames": frames,
                "fps": float(spec.get("fps", 8)),
            }
        loaded[char_name] = sequences
    return loaded


def active_clip(clips: list[dict], character: str, sec: float) -> dict | None:
    matches = [c for c in clips if c["character"] == character and c["start"] <= sec < c["end"]]
    return matches[-1] if matches else None


def char_state(name: str, char: dict, clips: list[dict], loaded: dict, sec: float) -> dict:
    clip = active_clip(clips, name, sec)
    if clip is None:
        clip = {
            "sequence": char["default_sequence"],
            "start": 0,
            "end": 1,
            "x0": char["x"],
            "y0": char["y"],
            "x1": char["x"],
            "y1": char["y"],
            "anchor": "bottom",
            "layer": 0,
        }
        q = 0
    else:
        q = clamp((sec - clip["start"]) / max(1e-6, clip["end"] - clip["start"]))

    eased = interpolation(q, clip.get("ease", "linear"))
    x0, y0 = clip.get("x0", char["x"]), clip.get("y0", char["y"])
    x1, y1 = clip.get("x1", x0), clip.get("y1", y0)
    x, y = lerp(x0, x1, eased), lerp(y0, y1, eased)
    arc = float(clip.get("arc_height", 0))
    height = arc * math.sin(math.pi * q)
    y -= height
    turns = float(clip.get("rotation_turns", 0))
    angle = lerp(float(clip.get("rotation_start", 0)),
                 float(clip.get("rotation_end", turns * 360)), eased)

    seq_name = clip["sequence"]
    seq = loaded[name][seq_name]
    if clip.get("hold_frame") is None:
        frame_fps = float(clip.get("frame_fps", seq["fps"]))
        index = int((sec - clip.get("start", 0)) * frame_fps) % len(seq["frames"])
    else:
        index = int(clip["hold_frame"]) % len(seq["frames"])

    return {
        "sprite": seq["frames"][index],
        "x": x,
        "y": y,
        "ground_y": lerp(y0, y1, eased),
        "height": max(0, height),
        "angle": angle,
        "anchor": clip.get("anchor", "bottom"),
        "layer": int(clip.get("layer", 0)),
    }


def paste_sprite(canvas: Image.Image, state: dict, shake: tuple[int, int]) -> None:
    sprite = state["sprite"]
    if state["angle"]:
        sprite = sprite.rotate(state["angle"], resample=Image.Resampling.NEAREST, expand=True)
    x, y = state["x"] + shake[0], state["y"] + shake[1]
    if state["anchor"] == "center":
        pos = (round(x - sprite.width / 2), round(y - sprite.height / 2))
    else:
        pos = (round(x - sprite.width / 2), round(y - sprite.height))
    canvas.alpha_composite(sprite, pos)


def draw_shadow(draw: ImageDraw.ImageDraw, state: dict, spec: list, shake: tuple[int, int]) -> None:
    half_w, half_h = int(spec[0]), int(spec[1])
    squash = max(0.25, 1 - state["height"] / 170)
    half_w = max(4, round(half_w * squash))
    x, y = state["x"] + shake[0], state["ground_y"] + shake[1]
    draw.ellipse((round(x - half_w), round(y - half_h), round(x + half_w),
                  round(y + half_h)), fill=(10, 25, 20, round(90 * squash)))


def starburst(draw: ImageDraw.ImageDraw, x: int, y: int, radius: int, phase: float) -> None:
    for ring, color in enumerate(((255, 252, 214, 255), (255, 222, 72, 255), (255, 117, 45, 255))):
        outer = max(2, radius - ring * 5)
        inner = max(1, outer // 3)
        points = []
        for i in range(16):
            angle = phase + i * math.pi / 8
            r = outer if i % 2 == 0 else inner
            points.append((round(x + math.cos(angle) * r), round(y + math.sin(angle) * r)))
        draw.polygon(points, fill=color)


def timed_position(effect: dict, sec: float) -> tuple[float, float, float]:
    q = clamp((sec - effect["start"]) / max(1e-6, effect["end"] - effect["start"]))
    return (
        lerp(effect.get("x0", 0), effect.get("x1", effect.get("x0", 0)), q),
        lerp(effect.get("y0", 0), effect.get("y1", effect.get("y0", 0)), q),
        q,
    )


def draw_effects(draw: ImageDraw.ImageDraw, effects: list[dict], sec: float, frame_index: int) -> None:
    for effect in effects:
        if effect["type"] == "impact":
            continue
        if not (effect["start"] <= sec < effect["end"]):
            continue
        x, y, q = timed_position(effect, sec)
        amount = float(effect.get("amount", 1))
        if effect["type"] == "speed_lines":
            for i, length in enumerate((34, 26, 18, 12)):
                yy = round(y - 22 + i * 14)
                xx = round(x - 32 - i * 8)
                color = ((255, 245, 158, 210), (255, 197, 49, 185), (93, 42, 57, 150))[i % 3]
                draw.rectangle((xx - round(length * amount), yy, xx, yy + 2), fill=color)
        elif effect["type"] == "dust":
            rng = np.random.default_rng(frame_index + 12345)
            strength = amount * math.sin(math.pi * q)
            for i in range(round(13 * strength)):
                dx = int(rng.integers(-28, 29) * strength)
                dy = int(rng.integers(-7, 3) - strength * rng.integers(0, 16))
                size = int(rng.choice([2, 3, 4, 5]))
                color = ((194, 147, 75, 190), (234, 196, 110, 210), (80, 68, 53, 150))[i % 3]
                draw.rectangle((round(x + dx), round(y + dy), round(x + dx + size),
                                round(y + dy + size)), fill=color)


def impact_state(effects: list[dict], sec: float, frame_index: int) -> tuple[tuple[int, int], list]:
    shake = (0, 0)
    active = []
    for effect in effects:
        if effect["type"] != "impact":
            continue
        q = sec - effect["time"]
        if 0 <= q < effect.get("duration", 0.35):
            decay = 1 - q / effect.get("duration", 0.35)
            amp = round(effect.get("shake", 0) * decay)
            shake = (amp if frame_index % 2 == 0 else -amp,
                     amp // 2 if frame_index % 3 == 0 else -(amp // 2))
            active.append((effect, q))
    return shake, active


def draw_texts(canvas: Image.Image, texts: list[dict], sec: float, width: int) -> None:
    font = ImageFont.load_default()
    for spec in texts:
        if not (spec["start"] <= sec < spec["end"]):
            continue
        fade = float(spec.get("fade", 0.35))
        visible = min(1, (sec - spec["start"]) / max(1e-6, fade),
                      (spec["end"] - sec) / max(1e-6, fade))
        tiny = Image.new("RGBA", (width // 2, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tiny)
        bbox = draw.textbbox((0, 0), spec["text"], font=font)
        x = (tiny.width - (bbox[2] - bbox[0])) // 2
        alpha = round(255 * clamp(visible))
        shadow = tuple(spec.get("shadow", [18, 22, 24])) + (alpha,)
        color = tuple(spec.get("color", [255, 241, 174])) + (alpha,)
        draw.text((x + 1, 9), spec["text"], font=font, fill=shadow)
        draw.text((x, 8), spec["text"], font=font, fill=color)
        big = tiny.resize((width, 64), Image.Resampling.NEAREST)
        canvas.alpha_composite(big, (0, int(spec.get("y", 276))))


def synth_audio(path: Path, duration: float, audio_spec: dict) -> None:
    sample_rate = 44100
    count = round(duration * sample_rate)
    audio = np.zeros(count, dtype=np.float64)
    chip = audio_spec.get("chiptune", {})
    if chip.get("enabled"):
        notes = chip.get("notes", [164.81, 196, 246.94, 293.66])
        beat = float(chip.get("beat", 0.375))
        gain = float(chip.get("gain", 0.035))
        for i in range(math.ceil(duration / beat)):
            start = int(i * beat * sample_rate)
            end = min(count, int((i + 0.78) * beat * sample_rate))
            tt = np.arange(end - start) / sample_rate
            env = np.minimum(1, tt * 35) * np.exp(-tt * 5.2)
            audio[start:end] += gain * env * np.sign(np.sin(2 * math.pi * notes[i % len(notes)] * tt))

    for event in audio_spec.get("events", []):
        start = int(event["time"] * sample_rate)
        end = min(count, start + int(event["duration"] * sample_rate))
        tt = np.arange(end - start) / sample_rate
        if event["type"] == "noise":
            rng = np.random.default_rng(int(event.get("seed", 1)))
            signal = rng.uniform(-1, 1, end - start)
            env = np.exp(-tt * float(event.get("decay", 7)))
        else:
            f0, f1 = float(event["f0"]), float(event.get("f1", event["f0"]))
            freq = f0 + (f1 - f0) * (tt / max(event["duration"], 1e-6))
            phase = 2 * math.pi * np.cumsum(freq) / sample_rate
            signal = np.sign(np.sin(phase)) if event.get("wave") == "square" else np.sin(phase)
            env = np.sin(np.pi * np.minimum(1, tt / event["duration"])) ** 1.5
        audio[start:end] += float(event.get("gain", 0.1)) * env * signal

    peak = max(1, np.abs(audio).max() / 0.94)
    pcm = np.int16(np.clip(audio / peak, -1, 1) * 32767)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def render(project: Path) -> Path:
    spec = json.loads((project / "short.json").read_text(encoding="utf-8"))
    width, height = map(int, spec["canvas"])
    fps, duration = int(spec["fps"]), float(spec["duration"])
    output = project / spec.get("output", "output/short.mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    previews = project / "previews"
    previews.mkdir(exist_ok=True)
    background = Image.open(project / spec["background"]).convert("RGBA")
    if background.size != (width, height):
        raise SystemExit(f"background must be {width}x{height}, got {background.size}")
    loaded = load_sequences(project, spec["characters"])
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required on PATH")

    silent = output.with_name(output.stem + "-silent.mp4")
    audio_path = output.with_name(output.stem + "-audio.wav")
    encode = [
        ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an",
        "-vf", f"scale={width*int(spec.get('delivery_scale', 2))}:"
               f"{height*int(spec.get('delivery_scale', 2))}:flags=neighbor",
        "-c:v", "libx264", "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p",
        str(silent),
    ]
    proc = subprocess.Popen(encode, stdin=subprocess.PIPE)
    assert proc.stdin
    frame_count = round(duration * fps)
    preview_indices = {0, frame_count // 4, frame_count // 2, frame_count * 3 // 4, frame_count - 1}

    for index in range(frame_count):
        sec = index / fps
        shake, impacts = impact_state(spec.get("effects", []), sec, index)
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        frame.alpha_composite(background, shake)
        draw = ImageDraw.Draw(frame, "RGBA")
        draw_effects(draw, spec.get("effects", []), sec, index)

        states = []
        for name, char in spec["characters"].items():
            state = char_state(name, char, spec.get("clips", []), loaded, sec)
            state["name"] = name
            states.append(state)
        for state in sorted(states, key=lambda item: (item["layer"], item["ground_y"])):
            draw_shadow(draw, state, spec["characters"][state["name"]].get("shadow", [20, 4]), shake)
        for state in sorted(states, key=lambda item: (item["layer"], item["ground_y"])):
            paste_sprite(frame, state, shake)

        for effect, elapsed in impacts:
            starburst(draw, int(effect["x"] + shake[0]), int(effect["y"] + shake[1]),
                      round(effect.get("radius", 30) * (1 - elapsed * 0.5)), elapsed)
            flash = float(effect.get("flash", 0))
            if flash and elapsed < flash:
                alpha = round(210 * (1 - elapsed / flash))
                draw.rectangle((0, 0, width, height), fill=(255, 251, 224, alpha))
        draw_texts(frame, spec.get("texts", []), sec, width)
        if index in preview_indices:
            frame.save(previews / f"preview-{index:04d}.png")
        proc.stdin.write(frame.convert("RGB").tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg video encode failed")
    synth_audio(audio_path, duration, spec.get("audio", {}))
    subprocess.run([
        ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio_path),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(output),
    ], check=True)
    print(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    render(Path(args.project).expanduser().resolve())


if __name__ == "__main__":
    main()

