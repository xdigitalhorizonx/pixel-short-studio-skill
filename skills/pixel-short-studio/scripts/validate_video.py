#!/usr/bin/env python3
"""Validate a pixel-short MP4 and write a timeline contact sheet."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--expect-fps", type=float, default=30)
    parser.add_argument("--min-duration", type=float, default=15)
    parser.add_argument("--max-duration", type=float, default=30)
    parser.add_argument("--contact-sheet")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise SystemExit("ffmpeg and ffprobe are required on PATH")

    raw = subprocess.check_output([
        ffprobe, "-v", "error", "-count_frames",
        "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,"
        "pix_fmt,r_frame_rate,nb_read_frames,sample_rate,channels",
        "-of", "json", str(video),
    ], text=True)
    report = json.loads(raw)
    streams = report["streams"]
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    failures = []
    duration = float(report["format"]["duration"])
    if not (args.min_duration <= duration <= args.max_duration):
        failures.append(f"duration {duration:.3f}s outside {args.min_duration}–{args.max_duration}s")
    if not video_stream:
        failures.append("missing video stream")
    else:
        num, den = map(float, video_stream["r_frame_rate"].split("/"))
        fps = num / den
        if abs(fps - args.expect_fps) > 0.01:
            failures.append(f"fps {fps:.3f} does not match {args.expect_fps}")
        if video_stream.get("codec_name") != "h264":
            failures.append("video codec is not h264")
        if video_stream.get("pix_fmt") != "yuv420p":
            failures.append("pixel format is not yuv420p")
        actual_frames = int(video_stream.get("nb_read_frames", 0))
        if abs(actual_frames - round(duration * fps)) > 1:
            failures.append("frame count does not match duration × fps")
        if video_stream.get("width", 0) % 2 or video_stream.get("height", 0) % 2:
            failures.append("delivery dimensions are not even")
    if not audio_stream:
        failures.append("missing audio stream")

    contact = Path(args.contact_sheet).expanduser().resolve() if args.contact_sheet else (
        video.parent / f"{video.stem}-contact-sheet.png"
    )
    interval = max(0.5, duration / 15)
    subprocess.run([
        ffmpeg, "-y", "-loglevel", "error", "-i", str(video),
        "-vf", f"fps=1/{interval},scale=320:180:flags=neighbor,"
               "tile=4x4:padding=2:margin=2",
        "-frames:v", "1", str(contact),
    ], check=True)

    print(json.dumps({
        "video": str(video),
        "contact_sheet": str(contact),
        "duration": duration,
        "streams": streams,
        "failures": failures,
    }, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

