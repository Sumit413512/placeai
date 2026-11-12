"""Original, deterministic concept-first teaching animations.

All elements are drawn locally with Pillow and encoded by the existing PyAV
pipeline. No third-party visual assets, prompts or reference-video frames are
copied. This module never modifies or reinterprets the supplied PlaceAI logo.

The animation clock is a *measured scene duration*, not word-level alignment.
Source-grounded values and labels are validated by VideoStoryboard before use.
"""
from __future__ import annotations

from functools import lru_cache
from math import floor

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 960, 540
INK = "#182b2a"
MUTED = "#5b7772"
PAPER = "#f3f9f4"
MINT = "#cae7d7"
JADE = "#087e67"
BURGUNDY = "#763e50"
AMBER = "#e8a54a"
CARD = "#ffffff"


def _ease(value):
    value = max(0.0, min(1.0, float(value)))
    return value * value * (3 - 2 * value)


@lru_cache(maxsize=1)
def _canvas():
    from app.learning_video_media import _place_brand_logo
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    drawing = ImageDraw.Draw(image)
    # Restrained original dot grid, not a lifted character or video frame.
    drawing.rounded_rectangle((14, 10, 946, 530), radius=25, fill="#f8fcf9")
    drawing.ellipse((620, -160, 1110, 240), fill="#e2f2e9")
    drawing.ellipse((-155, 245, 305, 725), fill="#e7f5ef")
    for y in range(116, 489, 27):
        for x in range(54, 919, 27):
            drawing.ellipse((x, y, x + 2, y + 2), fill="#e5eee8")
    drawing.rounded_rectangle((22, 12, 202, 78), radius=16, fill=CARD)
    # Paste the original image unchanged (size fitting is performed elsewhere).
    _place_brand_logo(image)
    return image


def _font(size, mono=False):
    from app.learning_video_media import _font as shared_font
    return shared_font(size, mono=mono)


def _fitted(text, max_width, size=24, minimum=13, mono=False):
    candidate = _font(size, mono=mono)
    while size > minimum and candidate.getlength(text) > max_width:
        size -= 1
        candidate = _font(size, mono=mono)
    if candidate.getlength(text) > max_width:
        raise ValueError("Animation label exceeds its safe visual bounds")
    return candidate


def _center(draw, x, y, text, fill=INK, size=24, max_width=200, mono=False):
    draw.text((round(x), round(y)), text, anchor="mm",
              font=_fitted(text, max_width, size=size, mono=mono), fill=fill)


def _progress(draw, phase, number, total):
    draw.line((55, 507, 902, 507), fill="#d9e6dd", width=4)
    draw.line((55, 507, 55 + int(847 * _ease(phase)), 507), fill=JADE, width=4)
    draw.text((844, 520), f"{number:02} / {total:02}",
              font=_font(13), fill=BURGUNDY)


def _header(draw, scene, number):
    title = scene["title"]
    if len(title) > 65:
        raise ValueError("Animation title exceeds its permitted length")
    draw.text((48, 101), "PLACEAI  /  VISUAL LEARNING",
              font=_font(14), fill=JADE)
    draw.text((48, 127), title,
              font=_fitted(title, 830, size=33, minimum=19), fill=INK)
    draw.rounded_rectangle((48, 173, 912, 177), radius=2, fill=MINT)


def _takeaway(draw, text):
    draw.rounded_rectangle((90, 451, 870, 495), radius=13,
                           fill="#e4f2eb", outline="#b7d7c8", width=2)
    _center(draw, 480, 473, text, fill=INK, size=19, max_width=742)


def _arrow(draw, x1, y, x2, color=JADE, portion=1.0):
    if x2 <= x1:
        return
    tip = x1 + (x2 - x1) * _ease(portion)
    draw.line((x1, y, tip, y), fill=color, width=4)
    if portion >= .95:
        draw.polygon(((tip, y), (tip - 9, y - 6), (tip - 9, y + 6)), fill=color)


def _card(draw, box, *, highlighted=False, active=False):
    draw.rounded_rectangle(box, radius=14,
                           fill="#d7f0e5" if highlighted else CARD,
                           outline=BURGUNDY if active else ("#76bda3" if highlighted else "#c7d9cd"),
                           width=3 if active else 2)


def _node_sequence(draw, visual, phase, *, linked):
    items = visual["labels"]
    n = len(items)
    if linked and n > 7:
        raise ValueError("Linked list contains too many nodes for the safe viewport")
    gap = 18 if linked else 9
    span = 820 if not linked else 770
    box_width = min(108, (span - (n - 1) * gap) / n)
    block = n * box_width + (n - 1) * gap
    start = (960 - block) / 2 - (12 if linked else 0)
    focus = visual["focus_index"]
    mode = visual.get("action", "scan")
    # Show the complete random-access array immediately. Hiding sequential
    # items would misleadingly suggest that direct indexing requires a scan.
    # In scan/traverse mode the pointer walks only until the actual target.
    position = min(focus, max(0, floor(phase * (focus + 1))))
    active = focus if mode == "direct" else position
    for index, label in enumerate(items):
        x = start + index * (box_width + gap)
        y = 275 if linked else 282
        active_node = index == active and phase >= .06
        _card(draw, (x, y - 45, x + box_width, y + 43),
              highlighted=index == focus if mode == "direct" else index <= position,
              active=active_node)
        _center(draw, x + box_width / 2, y - 3, label,
                size=26, max_width=box_width - 12)
        if not linked:
            _center(draw, x + box_width / 2, y + 69, str(index),
                    fill=MUTED, size=16, max_width=box_width - 8)
        elif index < n - 1:
            # The arrow appears after its source node: this is a pointer, not a sum.
            _arrow(draw, x + box_width + 3, y, x + box_width + gap - 3,
                   portion=min(1.0, max(0.0, (phase * (n + 1) - index) / .7)))
    if linked and phase > .8:
        tip = start + (n - 1) * (box_width + gap) + box_width
        draw.rounded_rectangle((tip + 8, 248, min(912, tip + 56), 302), radius=12,
                               fill="#e4f2eb", outline="#b7d7c8", width=2)
        _center(draw, min(886, tip + 33), 274, "NULL",
                fill=MUTED, size=14, max_width=46)
    # A pointer follows the concept action with clearly located array indices.
    if phase > .08:
        x = start + active * (box_width + gap) + box_width / 2
        draw.polygon(((x - 9, 206), (x + 9, 206), (x, 222)), fill=BURGUNDY)
    label = "INDEX" if not linked and mode == "direct" else (
        "NEXT POINTER" if linked else "CURRENT")
    _center(draw, 480, 401, f"{label}: {items[active]}",
            fill=BURGUNDY, size=22, max_width=820)



def _linked_sum(draw, visual, phase):
    """Two reversed-digit linked lists and the validated resulting digit chain."""
    pairs = [
        ("A", visual["labels"], 235),
        ("B", visual["other_labels"], 319),
        ("SUM", visual["result_labels"], 402),
    ]
    for row, (name, items, cy) in enumerate(pairs):
        if (row == 1 and phase < .23) or (row == 2 and phase < .54):
            continue
        portion = (phase / .24 if row == 0 else (phase - .23) / .32
                   if row == 1 else (phase - .54) / .45)
        portion = max(0, min(1, portion))
        n = len(items)
        width = min(79, (732 - (n - 1) * 11) / n)
        gap = 11
        length = n * width + (n - 1) * gap
        start = 170 + max(0, (735 - length) / 2)
        draw.text((59, cy - 12), name, font=_font(18),
                  fill=BURGUNDY if row == 2 else JADE)
        revealed = min(n, max(1, floor(portion * (n + 1)) + 1))
        selected = min(n - 1, floor(portion * n))
        for i, digit in enumerate(items):
            if i >= revealed and portion < .98:
                continue
            x = start + i * (width + gap)
            _card(draw, (x, cy - 24, x + width, cy + 25),
                  highlighted=row == 2 or i <= selected,
                  active=i == selected)
            _center(draw, x + width / 2, cy, digit, size=21,
                    max_width=width - 10)
            if i > 0:
                _arrow(draw, x - gap + 1, cy, x - 2,
                       portion=min(1, max(0, portion * (n + 1) - (i - 1))))
    # The output is displayed only after both input chains have been taught.
    # The arithmetic itself has already been validated in VideoStoryboard.

def _bar_chart(draw, visual, phase):
    names, values = visual["labels"], visual["values"]
    max_val = max(values) if values else 1
    baseline = 408
    draw.line((100, baseline, 868, baseline), fill=MUTED, width=3)
    n = len(names)
    gap = 20
    box_width = min(108, (760 - gap * (n - 1)) / n)
    total = box_width * n + gap * (n - 1)
    start = (960 - total) / 2
    focus = visual["focus_index"]
    for index, (name, value) in enumerate(zip(names, values)):
        x = start + index * (box_width + gap)
        height = max(9, int(value / max_val * 165 * _ease(phase)))
        draw.rounded_rectangle((x, baseline - height, x + box_width, baseline),
                               radius=9, fill=BURGUNDY if index == focus else JADE)
        if phase > .22:
            _center(draw, x + box_width / 2, baseline - height - 17, str(value),
                    size=18, fill=INK, max_width=box_width)
        _center(draw, x + box_width / 2, 430, name, size=16, max_width=box_width)


def _flow(draw, visual, phase):
    items = visual["labels"]
    n = len(items)
    gap = 16
    box_width = min(163, (826 - gap * (n - 1)) / n)
    total = box_width * n + gap * (n - 1)
    start = (960 - total) / 2
    y = 299
    reached = min(n - 1, floor(max(0, phase) * n))
    for i, label in enumerate(items):
        x = start + i * (box_width + gap)
        if i and (i - 1) / n <= phase:
            _arrow(draw, x - gap + 1, y, x - 2,
                   portion=min(1, (phase * n - (i - 1)) / .8))
        if i > reached + 1 and phase < .97:
            continue
        _card(draw, (x, y - 42, x + box_width, y + 43),
              highlighted=i <= reached, active=i == reached)
        _center(draw, x + box_width / 2, y, label, size=19,
                max_width=box_width - 12)


def _compare(draw, visual, phase):
    labels = visual["labels"]
    n = len(labels)
    gap, left = 22, 70
    width = (820 - gap * (n - 1)) / n
    for i, label in enumerate(labels):
        x = left + i * (width + gap)
        amount = _ease(min(1, max(0, phase * (n + 1) - i)))
        height = 65 + 90 * amount
        top = 379 - height
        _card(draw, (x, top, x + width, 378),
              highlighted=amount > .65, active=i == visual["focus_index"])
        _center(draw, x + width / 2, top + height / 2, label, size=22,
                max_width=width - 24)


def animated_frame(scene, number, total, phase):
    """Render one original animated teaching frame from a validated storyboard.

    The logo is always drawn by the same untouched branding routine used for
    older media. The caller supplies phase=frame / measured scene frames.
    """
    visual = scene["visual"]
    if not visual or not visual.get("kind"):
        raise ValueError("A storyboard animation needs a visual kind")
    image = _canvas().copy()
    draw = ImageDraw.Draw(image)
    _header(draw, scene, number)
    kind = visual["kind"]
    if kind in {"array", "linked_list"}:
        _node_sequence(draw, visual, phase, linked=kind == "linked_list")
    elif kind == "linked_sum":
        _linked_sum(draw, visual, phase)
    elif kind == "bar_chart":
        _bar_chart(draw, visual, phase)
    elif kind in {"flow", "timeline"}:
        _flow(draw, visual, phase)
    elif kind == "compare":
        _compare(draw, visual, phase)
    elif kind == "code_trace":
        labels = visual["labels"]
        left, top = 97, 224
        draw.rounded_rectangle((76, 207, 884, 435), radius=15, fill="#1d2d32")
        active = min(len(labels) - 1, floor(phase * len(labels)))
        for i, line in enumerate(labels):
            if i > active + 1 and phase < .97:
                continue
            y = top + i * 26
            if y > 408:
                raise ValueError("Code trace has too many lines")
            if i == active:
                draw.rounded_rectangle((86, y - 3, 874, y + 24),
                                       radius=6, fill="#30494c")
            draw.text((left, y), f"{i+1:02d}  {line}",
                      font=_fitted(f"{i+1:02d}  {line}", 750,
                                   size=17, minimum=12, mono=True),
                      fill="#a7f0d5" if i == active else "#e4f3ec")
    else:
        raise ValueError("Unsupported storyboard animation")
    # Recap is not a duplicate language banner or a caption. It is the one
    # concept checkpoint visible while the spoken worked example resolves.
    if kind != "code_trace":
        _takeaway(draw, visual["takeaway"])
    _progress(draw, phase, number, total)
    return image
