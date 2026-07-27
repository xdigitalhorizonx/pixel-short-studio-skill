#!/usr/bin/env python3
"""Render TK Quota as a 30-second pixel short."""

from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE / "output"
FRAMES = HERE / "frames"

W, H = 640, 360
FPS = 30
DURATION = 30.0
FRAME_COUNT = round(FPS * DURATION)

FONT_PATH = Path(r"C:\Windows\Fonts\consola.ttf")
BOLD_PATH = Path(r"C:\Windows\Fonts\consolab.ttf")
MUSIC_SOURCE = HERE / "source" / "audio" / "tarkov-theme-1m50s-2m19s.mp3"
MUSIC_START = 0.0
MUSIC_DURATION = 29.0
MUSIC_VOLUME = 0.052
MUSIC_DELAY = 3.663
MUSIC_FADE_OUT_START = 28.5 - MUSIC_DELAY
DISCORD_LEAVE_SOURCE = HERE / "source" / "audio" / "discord-leave.mp3"
DISCORD_LEAVE_AT = 16.8
RAGE_QUIT_DURATION = 0.32
DISCORD_LEAVE_TRIM_START = 0.140204
DISCORD_LEAVE_TRIM_END = 0.872041
DISCORD_LEAVE_VOLUME = 0.12

# Per-frame side-mounted laser emitter and barrel slope in sprite-local pixels.
# These points are mapped directly onto the placed walk frame, so animation cannot drift.
LASER_MOUNTS = {
    1: [
        ((45, 56), 0.52),
        ((50, 56), 0.52),
        ((45, 56), 0.52),
        ((50, 56), 0.52),
    ],
    4: [
        ((67, 48), 0.60),
        ((57, 48), 0.60),
        ((67, 48), 0.60),
        ((60, 48), 0.60),
        ((60, 39), 0.16),
    ],
}

# Compact contact frames keep both boots under the body when movement stops.
STANDING_FRAMES = {1: 1, 2: 1, 3: 1, 4: 1}

def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def smooth(value: float) -> float:
    value = clamp(value)
    return value * value * (3 - 2 * value)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def turning_sprite(walk_frames: list[Image.Image], progress: float) -> Image.Image:
    """Use intact contact poses for a planted four-beat pixel-art pivot."""
    progress = clamp(progress)
    if progress < 0.25:
        return walk_frames[1]
    if progress < 0.50:
        return walk_frames[3]
    if progress < 0.75:
        return walk_frames[3].transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return walk_frames[1].transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def font(size: int = 11, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD_PATH if bold else FONT_PATH), size)


def load_walkers() -> dict[int, list[Image.Image]]:
    walkers = {
        operator: [
            Image.open(ASSETS / f"pmc{operator}-walk{frame}.png").convert("RGBA")
            for frame in range(4)
        ]
        for operator in range(1, 5)
    }
    walkers[4].append(Image.open(ASSETS / "pmc4-aim-original.png").convert("RGBA"))
    return walkers


def foot_baseline(sprite: Image.Image) -> int:
    """Find the boot line without treating a low rifle muzzle as the ground."""
    alpha = np.asarray(sprite.getchannel("A"))
    height, width = alpha.shape
    center = alpha[:, round(width * 0.22):round(width * 0.78)]
    ys = np.where(center > 32)[0]
    baseline = round(float(np.percentile(ys, 98))) if len(ys) else height - 1
    return baseline


def body_anchor_x(sprite: Image.Image) -> float:
    """Use the upper-body mass as the horizontal anchor so frame widths cannot jitter."""
    alpha = np.asarray(sprite.getchannel("A"))
    height, _width = alpha.shape
    yy, xx = np.indices(alpha.shape)
    xs = xx[(alpha > 160) & (yy < round(height * 0.58))]
    anchor = float(np.median(xs)) if len(xs) else sprite.width / 2
    return anchor


def anchor_paste(canvas: Image.Image, sprite: Image.Image, x: float, y: float,
                 use_foot_baseline: bool = True) -> tuple[int, int]:
    baseline = foot_baseline(sprite) if use_foot_baseline else sprite.height - 1
    horizontal_anchor = body_anchor_x(sprite) if use_foot_baseline else sprite.width / 2
    px, py = round(x - horizontal_anchor), round(y - baseline)
    canvas.alpha_composite(sprite, (px, py))
    return px, py


def draw_shadow(draw: ImageDraw.ImageDraw, x: float, y: float, width: int, alpha: int = 85) -> None:
    # Opaque terrain colors survive RGB export without turning into a black floating oval.
    draw.ellipse((round(x - width), round(y - 2), round(x + width), round(y + 2)),
                 fill=(53, 45, 31, 255))
    draw.line((round(x - width * 0.55), round(y), round(x + width * 0.55), round(y)),
              fill=(39, 35, 26, 255), width=1)


def fuzzy_laser(canvas: Image.Image, start: tuple[int, int], end: tuple[int, int],
                color: tuple[int, int, int], core_alpha: int = 92,
                glow_alpha: int = 20, dot_alpha: int = 150) -> Image.Image:
    """Composite a translucent pixel beam with a soft three-pixel halo."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    laser_draw = ImageDraw.Draw(overlay, "RGBA")
    laser_draw.line([start, end], fill=(*color, glow_alpha), width=3)
    laser_draw.line([start, end], fill=(*color, round(glow_alpha * 1.7)), width=2)
    laser_draw.line([start, end], fill=(*color, core_alpha), width=1)
    laser_draw.rectangle((end[0] - 1, end[1] - 1, end[0] + 1, end[1] + 1),
                         fill=(*color, dot_alpha))
    return Image.alpha_composite(canvas, overlay)


def mounted_laser(placement: tuple[Image.Image, int, int, int],
                  operator: int, end_x: int) -> tuple[tuple[int, int], tuple[int, int], float]:
    """Return a beam locked to the exact emitter and barrel direction of a placed frame."""
    _sprite, frame_index, px, py = placement
    (local_x, local_y), slope = LASER_MOUNTS[operator][frame_index]
    start = (px + local_x, py + local_y)
    end_x = max(start[0] + 1, min(W - 8, end_x))
    end = (end_x, round(start[1] + (end_x - start[0]) * slope))
    return start, end, slope


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=fnt) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def speech_bubble(canvas: Image.Image, text: str, x: int, y: int, target_x: int, target_y: int,
                  max_width: int = 260,
                  avoid_rects: list[tuple[int, int, int, int]] | None = None,
                  layout_text: str | None = None) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    fnt = font(11, bold=True)
    layout_lines = wrap_text(draw, layout_text or text, fnt, max_width - 20)
    lines = wrap_text(draw, text, fnt, max_width - 20)
    line_h = 15
    width = min(max_width,
                max(round(draw.textlength(line, font=fnt)) for line in layout_lines) + 20)
    height = len(layout_lines) * line_h + 16
    requested = (max(6, min(W - width - 6, x)), max(12, min(H - height - 12, y)))
    candidates = [
        requested,
        (max(6, min(W - width - 6, target_x - width // 2)), 48),
        (12, 48),
        (W - width - 12, 48),
        ((W - width) // 2, 48),
        (12, 96),
        (W - width - 12, 96),
    ]
    avoid_rects = avoid_rects or []
    x, y = candidates[0]
    for candidate_x, candidate_y in candidates:
        bubble_rect = (candidate_x - 4, candidate_y - 4,
                       candidate_x + width + 4, candidate_y + height + 4)
        if not any(
            bubble_rect[0] <= obstacle[2] and bubble_rect[2] >= obstacle[0]
            and bubble_rect[1] <= obstacle[3] and bubble_rect[3] >= obstacle[1]
            for obstacle in avoid_rects
        ):
            x, y = candidate_x, candidate_y
            break
    draw.rectangle((x + 3, y + 3, x + width + 3, y + height + 3), fill=(5, 8, 10, 150))
    draw.rectangle((x, y, x + width, y + height), fill=(21, 27, 28, 238),
                   outline=(188, 205, 183, 255), width=2)
    tail_x = max(x + 14, min(x + width - 14, target_x))
    draw.polygon([(tail_x - 7, y + height), (tail_x + 5, y + height),
                  (target_x, target_y)], fill=(21, 27, 28, 238))
    draw.line([(tail_x - 7, y + height), (target_x, target_y)],
              fill=(188, 205, 183, 255), width=2)
    draw.line([(target_x, target_y), (tail_x + 5, y + height)],
              fill=(188, 205, 183, 255), width=2)
    for index, line in enumerate(lines):
        draw.text((x + 10, y + 7 + index * line_h), line, font=fnt, fill=(235, 240, 225, 255))


def title_card(canvas: Image.Image, sec: float) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    fade = min(1, sec / 0.35, (1.5 - sec) / 0.35)
    draw.rectangle((0, 0, W, H), fill=(4, 8, 7, round(92 * fade)))
    big = font(31, bold=True)
    small = font(10, bold=True)
    text = "TK QUOTA"
    box = draw.textbbox((0, 0), text, font=big)
    x = (W - (box[2] - box[0])) // 2
    draw.text((x + 3, 42 + 3), text, font=big, fill=(3, 7, 6, round(235 * fade)))
    draw.text((x, 42), text, font=big, fill=(223, 231, 207, round(255 * fade)))
    sub = "A PIXEL SHORT"
    sx = round((W - draw.textlength(sub, font=small)) / 2)
    draw.text((sx, 82), sub, font=small, fill=(146, 171, 140, round(255 * fade)))


def forest_scene(sec: float, background: Image.Image, walkers: dict[int, list[Image.Image]],
                 fall_frames: list[Image.Image]) -> Image.Image:
    shot_time = 12.6
    # Freeze the tracking camera with the formation so stopped feet do not slide over terrain.
    scene_q = clamp((min(sec, shot_time) - 1.5) / 15.7)
    pan_x = round(lerp(0, background.width - W, scene_q))
    frame = background.crop((pan_x, 36, pan_x + W, 36 + H)).convert("RGBA")
    draw = ImageDraw.Draw(frame, "RGBA")

    post_shot = sec >= shot_time
    walking = 1.5 <= sec < shot_time
    phase = max(0, sec - 1.5)
    step = int(phase * 4)

    # Loose tactical formation. PMC 3 starts outside/lower and closes inward while answering.
    positions = {
        1: [535, 274],
        2: [410, 291],
    }
    shooter_y = lerp(245, 249, smooth((sec - 11.75) / 0.5))
    positions[4] = [145, shooter_y]
    if sec < 8.5:
        victim_q = 0
    else:
        victim_q = smooth((sec - 8.5) / 4.1)
    victim_x = lerp(255, 327, victim_q)
    victim_y = lerp(320, 301, victim_q)
    positions[3] = [victim_x, victim_y]

    shake_x = shake_y = 0
    if 0 <= sec - shot_time < 0.45:
        decay = 1 - (sec - shot_time) / 0.45
        amp = round(5 * decay)
        frame_number = round(sec * FPS)
        shake_x = amp if frame_number % 2 == 0 else -amp
        shake_y = amp // 2 if frame_number % 3 == 0 else -(amp // 2)

    # Shadows share the same flat clearing as the corrected boot baselines.
    for operator, (x, y) in sorted(positions.items(), key=lambda item: item[1][1]):
        if operator == 3 and post_shot:
            continue
        draw_shadow(draw, x + shake_x, y + shake_y + 1, 15 if operator != 2 else 17)

    # Draw standing/walking operators in painter order and retain exact frame placement.
    placements: dict[int, tuple[Image.Image, int, int, int]] = {}
    for operator, (x, y) in sorted(positions.items(), key=lambda item: item[1][1]):
        if operator == 3 and post_shot:
            continue
        frame_index = (
            (step + operator) % 4
            if walking
            else STANDING_FRAMES[operator]
        )
        bob = 0
        sprite = walkers[operator][frame_index]
        if operator == 4 and 12.0 <= sec < 13.05:
            frame_index = 4
            sprite = walkers[4][frame_index]
        if post_shot and operator in (1, 2):
            turn_q = clamp((sec - 12.85) / 1.75)
            sprite = turning_sprite(walkers[operator], turn_q)
        recoil_x = 0
        recoil_y = 0
        if operator == 4 and 0 <= sec - shot_time < 0.18:
            recoil_q = 1 - (sec - shot_time) / 0.18
            recoil_x = round(-3 * recoil_q)
            recoil_y = round(1 * recoil_q)
        px, py = anchor_paste(
            frame,
            sprite,
            x + shake_x + recoil_x,
            y + bob + shake_y + recoil_y,
        )
        placements[operator] = (sprite, frame_index, px, py)

    standing_rects = [
        (px, py, px + sprite.width - 1, py + sprite.height - 1)
        for sprite, _frame_index, px, py in placements.values()
    ]

    # PMC 1 carries a blue laser; the rear operator carries the green laser.
    if 3.2 <= sec < shot_time:
        blue_muzzle, blue_end, _blue_slope = mounted_laser(
            placements[1], 1, round(positions[1][0] + 175)
        )
        frame = fuzzy_laser(frame, blue_muzzle, blue_end, (65, 174, 255),
                            core_alpha=82, glow_alpha=16, dot_alpha=135)
        draw = ImageDraw.Draw(frame, "RGBA")

    killer_x, killer_y = positions[4]
    green_target_x = round(victim_x + 4) if sec >= 12.25 else round(killer_x + 220)
    muzzle, aligned_green_end, green_slope = mounted_laser(
        placements[4], 4, green_target_x
    )
    if 3.2 <= sec < shot_time:
        frame = fuzzy_laser(frame, muzzle, aligned_green_end, (64, 255, 122),
                            core_alpha=74, glow_alpha=15, dot_alpha=128)
        draw = ImageDraw.Draw(frame, "RGBA")

    # Shot, hard impact and non-graphic fall.
    fall_rect: tuple[int, int, int, int] | None = None
    if post_shot:
        elapsed = sec - shot_time
        if elapsed < 0.16:
            flash_strength = round(46 * (1 - elapsed / 0.16))
            flash = Image.new("RGBA", (W, H), (255, 244, 205, flash_strength))
            frame = Image.alpha_composite(frame, flash)
            draw = ImageDraw.Draw(frame, "RGBA")
            frame = fuzzy_laser(frame, muzzle, aligned_green_end, (88, 255, 138),
                                core_alpha=174, glow_alpha=48, dot_alpha=210)
            draw = ImageDraw.Draw(frame, "RGBA")
            outer_dx = 24
            outer_dy = round(outer_dx * green_slope)
            shoulder_dx = 10
            shoulder_dy = round(shoulder_dx * green_slope)
            draw.polygon([
                (muzzle[0], muzzle[1] - 2),
                (muzzle[0] + shoulder_dx, muzzle[1] + shoulder_dy - 8),
                (muzzle[0] + outer_dx, muzzle[1] + outer_dy),
                (muzzle[0] + shoulder_dx, muzzle[1] + shoulder_dy + 8),
                (muzzle[0], muzzle[1] + 2),
            ], fill=(255, 177, 48, 245))
            inner_dx = 16
            inner_dy = round(inner_dx * green_slope)
            draw.polygon([
                (muzzle[0], muzzle[1] - 1),
                (muzzle[0] + 7, muzzle[1] + round(7 * green_slope) - 4),
                (muzzle[0] + inner_dx, muzzle[1] + inner_dy),
                (muzzle[0] + 7, muzzle[1] + round(7 * green_slope) + 4),
                (muzzle[0], muzzle[1] + 1),
            ], fill=(255, 246, 177, 255))
            draw.line(
                (muzzle[0], muzzle[1], muzzle[0] + 19, muzzle[1] + round(19 * green_slope)),
                fill=(255, 255, 235, 255),
                width=2,
            )
            draw.rectangle(
                (muzzle[0] + 21, muzzle[1] + outer_dy - 3,
                 muzzle[0] + 23, muzzle[1] + outer_dy - 1),
                fill=(255, 211, 91, 230),
            )
        if elapsed < 0.28:
            fall_index = 0
        elif elapsed < 0.72:
            fall_index = 1
        elif elapsed < 1.35:
            fall_index = 2
        else:
            # The prior final pose had a cropped helmet; hold the intact grounded pose.
            fall_index = 2
        fall = fall_frames[fall_index]
        fall_x = victim_x + min(22, elapsed * 14)
        fall_y = victim_y + 2
        draw_shadow(draw, fall_x + shake_x, fall_y + shake_y + 1, 19, 75)
        fall_px, fall_py = anchor_paste(
            frame, fall, fall_x + shake_x, fall_y + shake_y, use_foot_baseline=False
        )
        fall_rect = (fall_px, fall_py, fall_px + fall.width - 1, fall_py + fall.height - 1)

    if 4.6 <= sec < 8.5:
        killer_top = placements[4][3]
        speech_bubble(frame, "guys does anyone have a green laser?", 22, 52,
                      round(killer_x), killer_top - 4, 255, standing_rects)
    response_full = "bro, I have a green las......"
    response_start = 10.85
    response_complete = shot_time - 0.12
    if response_start <= sec < shot_time:
        response_progress = clamp((sec - response_start) / (response_complete - response_start))
        visible_chars = max(1, round(len(response_full) * response_progress))
        response_text = response_full[:visible_chars]
        victim_top = placements[3][3]
        speech_bubble(frame, response_text, 250, 52,
                      round(victim_x), victim_top - 4, 245, standing_rects,
                      layout_text=response_full)
    if 14.20 <= sec < 16.65 and fall_rect is not None:
        front_top = placements[1][3]
        all_rects = standing_rects + [fall_rect]
        speech_bubble(
            frame,
            "hahahahahahahahahahahahahahahaha",
            318,
            52,
            round(positions[1][0]),
            front_top - 4,
            300,
            all_rects,
        )
    if 14.7 <= sec < 16.8 and fall_rect is not None:
        all_rects = standing_rects + [fall_rect]
        speech_bubble(frame, "I’m dead", 275, 112,
                      round((fall_rect[0] + fall_rect[2]) / 2), fall_rect[1] - 4,
                      120, all_rects)

    # Subtle letterbox and scene label.
    draw.rectangle((0, 0, W, 8), fill=(5, 8, 8, 255))
    draw.rectangle((0, H - 8, W, H), fill=(5, 8, 8, 255))
    if sec < 1.5:
        title_card(frame, sec)
    if DISCORD_LEAVE_AT <= sec < DISCORD_LEAVE_AT + RAGE_QUIT_DURATION:
        local = sec - DISCORD_LEAVE_AT
        alpha = 255 if local < 0.20 else round(255 * (1 - (local - 0.20) / 0.12))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay, "RGBA")
        flash_font = font(36 if local < 0.07 else 34, bold=True)
        flash_text = "RAGE QUIT"
        text_box = overlay_draw.textbbox((0, 0), flash_text, font=flash_font)
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        text_x = round((W - text_w) / 2)
        text_y = round((H - text_h) / 2) - 12
        overlay_draw.rounded_rectangle(
            (text_x - 17, text_y - 9, text_x + text_w + 17, text_y + text_h + 12),
            radius=5,
            fill=(8, 6, 7, round(alpha * 0.78)),
            outline=(255, 58, 48, alpha),
            width=2,
        )
        overlay_draw.text(
            (text_x + 3, text_y + 3),
            flash_text,
            font=flash_font,
            fill=(0, 0, 0, round(alpha * 0.92)),
        )
        overlay_draw.text(
            (text_x, text_y),
            flash_text,
            font=flash_font,
            fill=(255, 76, 58, alpha),
        )
        frame = Image.alpha_composite(frame, overlay)
    return frame


def discord_avatar(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple[int, int, int],
                   initials: str) -> None:
    draw.ellipse((x, y, x + 32, y + 32), fill=(*color, 255),
                 outline=(20, 21, 24, 255), width=2)
    fnt = font(10, bold=True)
    tx = x + round((32 - draw.textlength(initials, font=fnt)) / 2)
    draw.text((tx, y + 9), initials, font=fnt, fill=(245, 246, 247, 255))
    draw.ellipse((x + 23, y + 23, x + 32, y + 32), fill=(35, 165, 89, 255),
                 outline=(43, 45, 49, 255), width=2)


def discord_body(draw: ImageDraw.ImageDraw, message: str, x: int, y: int,
                 max_width: int) -> int:
    """Draw wrapped Discord-like body text with mention pills."""
    body_font = font(10)
    cursor_x = x
    cursor_y = y
    line_count = 1
    space_width = round(draw.textlength(" ", font=body_font))
    for word in message.split(" "):
        word_width = round(draw.textlength(word, font=body_font))
        if cursor_x > x and cursor_x + word_width > x + max_width:
            cursor_x = x
            cursor_y += 14
            line_count += 1
        mention = word.startswith("@")
        if mention:
            draw.rounded_rectangle((cursor_x - 2, cursor_y, cursor_x + word_width + 2,
                                    cursor_y + 13), radius=2, fill=(61, 69, 112, 255))
            text_color = (202, 211, 255, 255)
        else:
            text_color = (219, 222, 225, 255)
        draw.text((cursor_x, cursor_y), word, font=body_font, fill=text_color)
        cursor_x += word_width + space_width
    return line_count


def discord_message(draw: ImageDraw.ImageDraw, y: int, name: str, name_color: tuple[int, int, int],
                    message: str, timestamp: str, initials: str) -> int:
    avatar_x = 200
    text_x = 240
    discord_avatar(draw, avatar_x, y, name_color, initials)
    name_font = font(10, bold=True)
    draw.text((text_x, y), name, font=name_font, fill=(*name_color, 255))
    name_w = round(draw.textlength(name, font=name_font))
    draw.text((text_x + 6 + name_w, y + 2), timestamp, font=font(7),
              fill=(148, 155, 164, 255))
    lines = discord_body(draw, message, text_x, y + 15, 382)
    return y + max(42, 20 + lines * 14)


def discord_scene(sec: float) -> Image.Image:
    # Discord-like three-column shell: server rail, channel list and active chat.
    frame = Image.new("RGBA", (W, H), (49, 51, 56, 255))
    draw = ImageDraw.Draw(frame, "RGBA")
    rail_x = 48
    main_x = 190
    draw.rectangle((0, 0, rail_x, H), fill=(30, 31, 34, 255))
    draw.rectangle((rail_x, 0, main_x, H), fill=(43, 45, 49, 255))
    draw.rectangle((main_x, 0, W, H), fill=(49, 51, 56, 255))

    # Server rail.
    draw.rounded_rectangle((8, 8, 40, 40), radius=11, fill=(88, 101, 242, 255))
    draw.ellipse((16, 17, 32, 30), outline=(255, 255, 255, 255), width=2)
    draw.ellipse((20, 22, 22, 24), fill=(255, 255, 255, 255))
    draw.ellipse((26, 22, 28, 24), fill=(255, 255, 255, 255))
    draw.rounded_rectangle((8, 54, 40, 86), radius=10, fill=(88, 101, 242, 255))
    draw.text((15, 64), "TK", font=font(9, bold=True), fill=(255, 255, 255, 255))
    draw.rounded_rectangle((0, 61, 4, 79), radius=2, fill=(242, 243, 245, 255))
    for cy, label in [(106, "S"), (148, "D")]:
        draw.ellipse((8, cy - 16, 40, cy + 16), fill=(49, 51, 56, 255))
        tw = draw.textlength(label, font=font(10, bold=True))
        draw.text((24 - tw / 2, cy - 7), label, font=font(10, bold=True),
                  fill=(185, 187, 190, 255))
    draw.ellipse((8, 176, 40, 208), fill=(35, 165, 89, 255))
    draw.text((18, 184), "+", font=font(15, bold=True), fill=(255, 255, 255, 255))

    # Channel sidebar.
    draw.rectangle((rail_x, 0, main_x, 44), fill=(43, 45, 49, 255))
    draw.line((rail_x, 43, main_x, 43), fill=(31, 32, 35, 255), width=1)
    draw.text((60, 14), "TK TRACKER", font=font(10, bold=True), fill=(242, 243, 245, 255))
    draw.text((174, 14), "v", font=font(9, bold=True), fill=(181, 186, 193, 255))
    draw.text((58, 54), "V  TEXT CHANNELS", font=font(7, bold=True),
              fill=(148, 155, 164, 255))
    draw.text((64, 72), "#", font=font(13, bold=True), fill=(148, 155, 164, 255))
    draw.text((80, 74), "general", font=font(9), fill=(148, 155, 164, 255))
    draw.rounded_rectangle((54, 91, 184, 116), radius=4, fill=(64, 66, 73, 255))
    draw.text((64, 96), "#", font=font(13, bold=True), fill=(219, 222, 225, 255))
    draw.text((80, 98), "team-kill-tracker", font=font(8, bold=True),
              fill=(242, 243, 245, 255))
    draw.text((58, 132), "V  VOICE CHANNELS", font=font(7, bold=True),
              fill=(148, 155, 164, 255))
    draw.polygon([(64, 156), (68, 156), (73, 152), (73, 164), (68, 160), (64, 160)],
                 fill=(148, 155, 164, 255))
    draw.arc((70, 153, 78, 163), 285, 75, fill=(148, 155, 164, 255), width=1)
    draw.text((80, 153), "Patrol VC", font=font(9), fill=(148, 155, 164, 255))
    draw.ellipse((70, 174, 79, 183), fill=(35, 165, 89, 255))
    draw.text((84, 173), "Skydog", font=font(8), fill=(181, 186, 193, 255))
    draw.ellipse((70, 190, 79, 199), fill=(35, 165, 89, 255))
    draw.text((84, 189), "Zero", font=font(8), fill=(181, 186, 193, 255))

    # Signed-in user strip.
    draw.rectangle((rail_x, 318, main_x, H), fill=(35, 36, 40, 255))
    draw.ellipse((58, 327, 80, 349), fill=(46, 145, 220, 255))
    draw.text((65, 333), "Z", font=font(8, bold=True), fill=(255, 255, 255, 255))
    draw.ellipse((74, 343, 81, 350), fill=(35, 165, 89, 255),
                 outline=(35, 36, 40, 255), width=1)
    draw.text((86, 327), "Zero", font=font(8, bold=True), fill=(242, 243, 245, 255))
    draw.text((86, 339), "Online", font=font(7), fill=(148, 155, 164, 255))
    draw.ellipse((157, 330, 168, 341), outline=(181, 186, 193, 255), width=2)
    draw.ellipse((161, 334, 164, 337), fill=(181, 186, 193, 255))

    # Active-channel toolbar.
    draw.rectangle((main_x, 0, W, 44), fill=(49, 51, 56, 255))
    draw.line((main_x, 43, W, 43), fill=(31, 32, 35, 255), width=1)
    draw.text((202, 12), "#", font=font(15, bold=True), fill=(148, 155, 164, 255))
    draw.text((219, 14), "team-kill-tracker", font=font(10, bold=True),
              fill=(242, 243, 245, 255))
    draw.rectangle((503, 14, 513, 24), outline=(181, 186, 193, 255), width=1)
    draw.line((506, 17, 510, 17), fill=(181, 186, 193, 255))
    draw.line((506, 20, 510, 20), fill=(181, 186, 193, 255))
    draw.ellipse((526, 14, 532, 20), fill=(181, 186, 193, 255))
    draw.arc((523, 18, 535, 28), 195, 345, fill=(181, 186, 193, 255), width=2)
    draw.rounded_rectangle((550, 10, 624, 34), radius=4, fill=(30, 31, 34, 255))
    draw.text((558, 17), "Search", font=font(7), fill=(148, 155, 164, 255))
    draw.ellipse((610, 16, 617, 23), outline=(148, 155, 164, 255), width=1)
    draw.line((616, 22, 620, 26), fill=(148, 155, 164, 255), width=1)

    date_font = font(8, bold=True)
    date = "July 21, 2026"
    date_w = round(draw.textlength(date, font=date_font))
    center_x = round((main_x + W) / 2)
    draw.line((202, 58, center_x - date_w // 2 - 8, 58), fill=(78, 80, 88, 255))
    draw.line((center_x + date_w // 2 + 8, 58, 628, 58), fill=(78, 80, 88, 255))
    draw.text((center_x - date_w // 2, 52), date, font=date_font,
              fill=(148, 155, 164, 255))

    y = 68
    y = discord_message(
        draw, y, "Zero", (46, 145, 220),
        "i’m glad we made this tk tracker bc @skydog is now at 6 tks this month",
        "2 days ago", "Z",
    )

    local = sec - 17.2
    skydog_message = "someone switch out @Zero’s rounds for blanks bc he’s now at 14 tks this month"
    dimmy_message = "I'm gonna cu"
    sent = local >= 6.5
    if sent:
        y = discord_message(draw, y + 5, "Skydog", (223, 103, 92),
                            skydog_message, "Today at 12:14 AM", "S")

    zero_sent = local >= 8.0
    if zero_sent:
        y = discord_message(draw, y + 5, "Zero", (46, 145, 220),
                            "i’m working on setting a high score get fucked",
                            "Today at 12:14 AM", "Z")

    justscott_sent = local >= 9.3
    if justscott_sent:
        y = discord_message(draw, y + 5, "justscott", (94, 190, 132),
                            "no i think you're just stupid",
                            "Today at 12:14 AM", "JS")

    # Composer and live typing state.
    composer_y = 304
    draw.rounded_rectangle(
        (200, composer_y, 628, 350),
        radius=8,
        fill=(56, 58, 64, 255),
        outline=(82, 85, 94, 255),
        width=1,
    )
    draw.ellipse((209, 318, 229, 338), fill=(181, 186, 193, 255))
    draw.text((215, 319), "+", font=font(12, bold=True), fill=(64, 66, 73, 255))
    draw.text((240, 318), "Message #team-kill-tracker", font=font(9, bold=True),
              fill=(190, 194, 201, 255))
    draw.text((551, 319), "GIF", font=font(7, bold=True), fill=(181, 186, 193, 255))
    draw.ellipse((582, 319, 600, 337), outline=(181, 186, 193, 255), width=2)
    draw.ellipse((587, 324, 589, 326), fill=(181, 186, 193, 255))
    draw.ellipse((593, 324, 595, 326), fill=(181, 186, 193, 255))
    draw.arc((587, 324, 595, 333), 15, 165, fill=(181, 186, 193, 255), width=1)
    draw.line((617, 319, 617, 337), fill=(181, 186, 193, 255), width=1)
    draw.line((608, 328, 626, 328), fill=(181, 186, 193, 255), width=1)
    draw.line((612, 323, 622, 333), fill=(181, 186, 193, 255), width=1)
    draw.line((622, 323, 612, 333), fill=(181, 186, 193, 255), width=1)

    if 3.0 <= local < 6.5:
        q = clamp((local - 3.0) / 3.25)
        count = round(len(skydog_message) * q)
        typed = skydog_message[:count]
        draw.rounded_rectangle(
            (200, composer_y, 628, 350),
            radius=8,
            fill=(50, 52, 58, 255),
            outline=(95, 99, 110, 255),
            width=1,
        )
        composer_font = font(10, bold=True)
        lines = wrap_text(draw, typed, composer_font, 370)
        for index, line in enumerate(lines[-2:]):
            draw.text((214, 307 + index * 17), line, font=composer_font,
                      fill=(248, 249, 250, 255))
        draw.text((202, 289), "Skydog is typing…", font=font(8, bold=True),
                  fill=(206, 209, 214, 255))
    elif 6.5 <= local < 8.0:
        dots = "." * (1 + int(local * 3) % 3)
        draw.text((202, 289), f"Zero is typing{dots}", font=font(8, bold=True),
                  fill=(206, 209, 214, 255))
    elif 8.7 <= local < 9.3:
        dots = "." * (1 + int(local * 3) % 3)
        draw.text((202, 289), f"justscott is typing{dots}", font=font(8, bold=True),
                  fill=(206, 209, 214, 255))
    elif 9.8 <= local < 11.5:
        # Give "c" and "u" distinct beats, then hold the unfinished phrase before the cut.
        if local < 10.9:
            q = clamp((local - 9.8) / 1.1)
            typed = dimmy_message[:int(10 * q)]
        elif local < 11.15:
            typed = dimmy_message[:11]
        else:
            typed = dimmy_message
        draw.rounded_rectangle(
            (200, composer_y, 628, 350),
            radius=8,
            fill=(50, 52, 58, 255),
            outline=(95, 99, 110, 255),
            width=1,
        )
        composer_font = font(10, bold=True)
        draw.text((214, 315), typed, font=composer_font, fill=(248, 249, 250, 255))
        dots = "." * (1 + int(local * 3) % 3)
        draw.text((202, 289), f"Dimmy is typing{dots}", font=font(8, bold=True),
                  fill=(206, 209, 214, 255))
        cursor_x = 216 + round(draw.textlength(typed, font=composer_font))
        draw.rectangle((cursor_x, 312, cursor_x + 2, 329), fill=(248, 249, 250, 255))

    # Pixel cursor/activity blink.
    if int(sec * 2) % 2 == 0 and 3.0 <= local < 6.5:
        draw.rectangle((610, 309, 612, 326), fill=(248, 249, 250, 255))

    # Voice-channel laughter bubble appears immediately with the Discord scene.
    if 0 <= local < 2.25:
        bubble_alpha = 255 if local < 2.0 else round(255 * (1 - (local - 2.0) / 0.25))
        bubble_text = "hahahahahahahahaha"
        bubble_font = font(9, bold=True)
        bubble_w = round(draw.textlength(bubble_text, font=bubble_font)) + 18
        bubble_h = 27
        bubble_x = 132
        bubble_y = 163
        bubble = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bubble_draw = ImageDraw.Draw(bubble, "RGBA")
        bubble_draw.polygon(
            [(bubble_x, bubble_y + 9), (bubble_x - 13, bubble_y + 14),
             (bubble_x, bubble_y + 19)],
            fill=(32, 34, 38, bubble_alpha),
        )
        bubble_draw.rounded_rectangle(
            (bubble_x, bubble_y, bubble_x + bubble_w, bubble_y + bubble_h),
            radius=5,
            fill=(32, 34, 38, bubble_alpha),
            outline=(112, 116, 128, bubble_alpha),
            width=1,
        )
        bubble_draw.text(
            (bubble_x + 9, bubble_y + 7),
            bubble_text,
            font=bubble_font,
            fill=(242, 243, 245, bubble_alpha),
        )
        frame = Image.alpha_composite(frame, bubble)
    return frame


def end_card(sec: float) -> Image.Image:
    frame = Image.new("RGBA", (W, H), (4, 5, 6, 255))
    draw = ImageDraw.Draw(frame, "RGBA")
    q = clamp((sec - 28.7) / 0.25)
    title = "THE END"
    fnt = font(34, bold=True)
    x = round((W - draw.textlength(title, font=fnt)) / 2)
    draw.text((x + 3, 151 + 3), title, font=fnt, fill=(0, 0, 0, round(240 * q)))
    draw.text((x, 151), title, font=fnt, fill=(231, 232, 224, round(255 * q)))
    return frame


def synth_audio(path: Path) -> None:
    sr = 44100
    count = round(DURATION * sr)
    audio = np.zeros(count, dtype=np.float64)
    rng = np.random.default_rng(7461)

    # Forest air: slow filtered noise, kept subtle.
    start, end = int(1.5 * sr), int(17.2 * sr)
    noise = rng.normal(0, 1, end - start)
    kernel = np.ones(900) / 900
    air = np.convolve(noise, kernel, mode="same")
    air /= max(1e-6, np.max(np.abs(air)))
    audio[start:end] += air * 0.035

    def tone(at: float, duration: float, f0: float, f1: float, gain: float,
             wave_type: str = "sine") -> None:
        s = int(at * sr)
        e = min(count, s + int(duration * sr))
        tt = np.arange(e - s) / sr
        freq = f0 + (f1 - f0) * tt / max(duration, 1e-6)
        phase = 2 * math.pi * np.cumsum(freq) / sr
        signal = np.sign(np.sin(phase)) if wave_type == "square" else np.sin(phase)
        env = np.sin(np.pi * np.minimum(1, tt / duration)) ** 1.4
        audio[s:e] += signal * env * gain

    def noise_burst(at: float, duration: float, gain: float, seed: int, decay: float) -> None:
        s = int(at * sr)
        e = min(count, s + int(duration * sr))
        tt = np.arange(e - s) / sr
        burst = np.random.default_rng(seed).uniform(-1, 1, e - s)
        audio[s:e] += burst * np.exp(-tt * decay) * gain

    def distant_gunshot(at: float, gain: float, seed: int) -> None:
        """Muffled report with a quiet delayed reflection."""
        duration = 0.72
        s = int(at * sr)
        e = min(count, s + int(duration * sr))
        tt = np.arange(e - s) / sr
        raw = np.random.default_rng(seed).uniform(-1, 1, e - s)
        muffled = np.convolve(raw, np.ones(24) / 24, mode="same")
        muffled /= max(1e-6, np.max(np.abs(muffled)))
        audio[s:e] += muffled * np.exp(-tt * 7.5) * gain
        tone(at, 0.58, 96, 43, gain * 0.72)

        echo_at = at + 0.24
        echo_s = int(echo_at * sr)
        echo_e = min(count, echo_s + int(0.48 * sr))
        echo_t = np.arange(echo_e - echo_s) / sr
        echo_raw = np.random.default_rng(seed + 100).uniform(-1, 1, echo_e - echo_s)
        echo = np.convolve(echo_raw, np.ones(42) / 42, mode="same")
        echo /= max(1e-6, np.max(np.abs(echo)))
        audio[echo_s:echo_e] += echo * np.exp(-echo_t * 8.5) * gain * 0.24

    def dirt_footstep(at: float, gain: float, seed: int) -> None:
        """Dry heel impact, granular dirt crunch and a softer trailing scuff."""
        duration = 0.14
        s = int(at * sr)
        e = min(count, s + int(duration * sr))
        tt = np.arange(e - s) / sr
        step_rng = np.random.default_rng(seed)
        raw = step_rng.uniform(-1, 1, e - s)

        fine = np.convolve(raw, np.ones(4) / 4, mode="same")
        coarse = np.convolve(raw, np.ones(38) / 38, mode="same")
        grit = fine - coarse
        attack = np.minimum(1, tt / 0.003)
        heel_env = attack * np.exp(-tt * 31)
        scuff_env = np.where(tt >= 0.036, np.exp(-(tt - 0.036) * 25), 0)
        audio[s:e] += grit * (heel_env + scuff_env * 0.34) * gain

        # A few irregular grains suggest loose pebbles rather than a flat hard surface.
        for grain_index in range(5):
            grain_start = int(step_rng.uniform(0.012, 0.095) * sr)
            grain_length = int(step_rng.uniform(0.0025, 0.0065) * sr)
            grain_end = min(e - s, grain_start + grain_length)
            if grain_end <= grain_start:
                continue
            grain = step_rng.uniform(-1, 1, grain_end - grain_start)
            grain *= np.hanning(max(2, grain_end - grain_start))
            audio[s + grain_start:s + grain_end] += grain * gain * (0.23 - grain_index * 0.018)

        tone(at, 0.075, 82, 48, gain * 0.32)

    # Staggered footsteps on dry forest dirt.
    for index, at in enumerate(np.arange(1.7, 12.5, 0.42)):
        strength = 0.044 + (index % 4) * 0.002
        dirt_footstep(float(at), strength, 1000 + index)

    # Sparse, irregular rifle fire far beyond the clearing.
    distant_gunshot(4.15, 0.052, 3101)
    distant_gunshot(7.02, 0.046, 3102)
    distant_gunshot(7.36, 0.041, 3103)
    distant_gunshot(10.08, 0.048, 3104)

    # Rifle report and gear/body impact.
    noise_burst(12.6, 0.42, 0.52, 2201, 11)
    tone(12.6, 0.46, 115, 38, 0.48)
    noise_burst(13.25, 0.20, 0.12, 2202, 20)
    tone(13.28, 0.18, 74, 42, 0.14)

    # Chat typing and sends.
    for index, at in enumerate(np.arange(20.2, 23.42, 0.095)):
        tone(float(at), 0.018, 1450 + (index % 4) * 90, 1100, 0.018, "square")
    tone(23.7, 0.18, 520, 760, 0.09, "square")
    for index, at in enumerate(np.arange(23.85, 25.05, 0.16)):
        tone(float(at), 0.016, 1250 + (index % 3) * 100, 960, 0.014, "square")
    tone(25.2, 0.20, 480, 820, 0.10, "square")
    tone(26.5, 0.20, 520, 860, 0.10, "square")
    tone(28.72, 0.45, 220, 110, 0.11)

    peak = max(1, np.max(np.abs(audio)) / 0.94)
    pcm = np.int16(np.clip(audio / peak, -1, 1) * 32767)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())


def render() -> Path:
    OUT.mkdir(exist_ok=True)
    FRAMES.mkdir(exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required")
    if not MUSIC_SOURCE.exists():
        raise SystemExit(f"music source not found: {MUSIC_SOURCE}")
    if not DISCORD_LEAVE_SOURCE.exists():
        raise SystemExit(f"Discord leave sound not found: {DISCORD_LEAVE_SOURCE}")

    background = Image.open(ASSETS / "forest-bg-wide.png").convert("RGBA")
    walkers = load_walkers()
    fall_frames = [
        Image.open(ASSETS / f"pmc3-fall{index}.png").convert("RGBA")
        for index in range(4)
    ]
    silent = OUT / "tk-quota-silent.mp4"
    audio = OUT / "tk-quota-audio.wav"
    final = OUT / "tk-quota.mp4"
    command = [
        ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an",
        "-vf", "scale=1280:720:flags=neighbor", "-c:v", "libx264", "-preset", "medium",
        "-crf", "15", "-pix_fmt", "yuv420p", str(silent),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin
    preview_times = [0.8, 3.0, 6.2, 10.4, 11.4, 12.5, 12.65, 15.4, 18.2, 22.0, 24.3, 26.4, 27.5, 28.67, 29.2]
    preview_frames = {round(time * FPS): time for time in preview_times}

    for index in range(FRAME_COUNT):
        sec = index / FPS
        if sec < 17.2:
            frame = forest_scene(sec, background, walkers, fall_frames)
        elif sec < 28.7:
            frame = discord_scene(sec)
        else:
            frame = end_card(sec)
        if index in preview_frames:
            frame.save(FRAMES / f"preview-{preview_frames[index]:05.2f}.png")
        process.stdin.write(frame.convert("RGB").tobytes())

    process.stdin.close()
    if process.wait() != 0:
        raise SystemExit("video encode failed")
    synth_audio(audio)
    mix_filter = (
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[sfx];"
        f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"volume={MUSIC_VOLUME},afade=t=in:st=0:d=2.0,"
        f"afade=t=out:st={MUSIC_FADE_OUT_START}:d=1.5,"
        f"adelay={round(MUSIC_DELAY * 1000)}|{round(MUSIC_DELAY * 1000)}[music];"
        f"[3:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"atrim=start={DISCORD_LEAVE_TRIM_START}:end={DISCORD_LEAVE_TRIM_END},"
        f"asetpts=PTS-STARTPTS,volume={DISCORD_LEAVE_VOLUME},"
        f"adelay={round(DISCORD_LEAVE_AT * 1000)}|{round(DISCORD_LEAVE_AT * 1000)}[leave];"
        "[sfx][music]amix=inputs=2:duration=longest:dropout_transition=0[base];"
        "[base][leave]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.96[aout]"
    )
    subprocess.run([
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(silent), "-i", str(audio),
        "-ss", str(MUSIC_START), "-t", str(MUSIC_DURATION), "-i", str(MUSIC_SOURCE),
        "-i", str(DISCORD_LEAVE_SOURCE),
        "-filter_complex", mix_filter, "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        "-movflags", "+faststart", str(final),
    ], check=True)
    print(final)
    return final


if __name__ == "__main__":
    render()
