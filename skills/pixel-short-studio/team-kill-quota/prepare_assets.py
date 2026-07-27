#!/usr/bin/env python3
"""Prepare generated keyed art for the Team Kill Quota renderer."""

from pathlib import Path

from PIL import Image


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source" / "generated"
ASSETS = HERE / "assets"
ASSETS.mkdir(exist_ok=True)


def trim_alpha(image: Image.Image) -> Image.Image:
    bbox = image.getbbox()
    return image.crop(bbox) if bbox else image


def remove_detached_ground_shadow(image: Image.Image) -> Image.Image:
    """Remove a separated generated oval below the boots while preserving the operator."""
    image = image.copy()
    alpha = image.getchannel("A")
    row_has_pixels = [
        alpha.crop((0, y, image.width, y + 1)).getbbox() is not None
        for y in range(image.height)
    ]
    start = round(image.height * 0.55)
    for y in range(start, image.height - 2):
        if row_has_pixels[y]:
            continue
        gap_end = y
        while gap_end < image.height and not row_has_pixels[gap_end]:
            gap_end += 1
        if gap_end - y >= 2 and any(row_has_pixels[gap_end:]):
            cleared = Image.new("L", image.size, 0)
            cleared.paste(alpha.crop((0, 0, image.width, y)), (0, 0))
            image.putalpha(cleared)
            break
    return trim_alpha(image)


def resize_by_scale(image: Image.Image, scale: float) -> Image.Image:
    return image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.NEAREST,
    )


def split_grid(image: Image.Image, cols: int, rows: int) -> list[list[Image.Image]]:
    output = []
    for row in range(rows):
        row_frames = []
        y0, y1 = round(row * image.height / rows), round((row + 1) * image.height / rows)
        for col in range(cols):
            x0, x1 = round(col * image.width / cols), round((col + 1) * image.width / cols)
            row_frames.append(trim_alpha(image.crop((x0, y0, x1, y1))))
        output.append(row_frames)
    return output


def main() -> None:
    forest = Image.open(SOURCE / "forest-flat-generated.png").convert("RGB")
    # Keep a larger-than-frame plate so the renderer can pan through the trees.
    target_ratio = 16 / 9
    if forest.width / forest.height > target_ratio:
        crop_w = round(forest.height * target_ratio)
        x0 = (forest.width - crop_w) // 2
        forest = forest.crop((x0, 0, x0 + crop_w, forest.height))
    else:
        crop_h = round(forest.width / target_ratio)
        y0 = (forest.height - crop_h) // 2
        forest = forest.crop((0, y0, forest.width, y0 + crop_h))
    forest.resize((768, 432), Image.Resampling.NEAREST).save(ASSETS / "forest-bg-wide.png")

    walk = Image.open(SOURCE / "pmc-walk-grid-alpha-v2.png").convert("RGBA")
    rows = split_grid(walk, 4, 4)
    rows = [[remove_detached_ground_shadow(frame) for frame in row] for row in rows]
    for row_index, frames in enumerate(rows, 1):
        max_height = max(frame.height for frame in frames)
        scale = 80 / max_height
        for frame_index, frame in enumerate(frames):
            resize_by_scale(frame, scale).save(ASSETS / f"pmc{row_index}-walk{frame_index}.png")

    fall = Image.open(SOURCE / "pmc-victim-fall-alpha.png").convert("RGBA")
    fall_frames = split_grid(fall, 4, 1)[0]
    standing_height = fall_frames[0].height
    scale = 80 / standing_height
    for index, frame in enumerate(fall_frames):
        resize_by_scale(frame, scale).save(ASSETS / f"pmc3-fall{index}.png")

    print(ASSETS)


if __name__ == "__main__":
    main()
