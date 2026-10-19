"""Turn a visual into positioned primitives on a 16 x 9 unit canvas.

This module is pure arithmetic. It knows nothing about Blender, so the layout can
be unit-tested without it. The Blender side (``render_bpy``) only translates the
primitives into scene objects.

Coordinates are in canvas units, origin at the bottom-left, y pointing up. The
canvas is 16 units wide and 9 units high, which matches a 16:9 frame.
"""

from __future__ import annotations

import textwrap

from scripts.blender_lesson.primitives import (
    CANVAS_H,
    CANVAS_W,
    Arrow,
    Box,
    Headline,
    LayoutError,
    Picture,
    Primitive,
)
from scripts.blender_lesson.spec import (
    ChecklistVisual,
    DialogueVisual,
    FlowVisual,
    RosterVisual,
    TextVisual,
    Visual,
)

_MARGIN = 1.0
_MID_Y = CANVAS_H / 2
BUBBLE_W = 8.4
BUBBLE_EDGE = 0.9
BUBBLE_WRAP_CHARS = 36
BUBBLE_LINE_H = 0.55
BUBBLE_NAME_H = 0.6
PORTRAIT_SIZE = 2.6
PORTRAIT_EDGE = 0.4
PORTRAIT_GAP = 0.3


def layout_visual(
    visual: Visual,
    *,
    narration: str = "",
    speaker_name: str = "",
    side: int = 0,
    portrait: str | None = None,
) -> tuple[Primitive, ...]:
    """Return the primitives for one scene's visual, deterministically.

    A dialogue visual needs the line it shows (``narration``), the speaker's
    on-screen name, and ``side``: 0 for the left of the frame, 1 for the right.
    """
    if isinstance(visual, DialogueVisual):
        return _bubble(narration, speaker_name, side, portrait)
    if isinstance(visual, FlowVisual):
        return _flow(visual.steps)
    if isinstance(visual, ChecklistVisual):
        return _checklist(visual.items)
    if isinstance(visual, RosterVisual):
        return _roster(visual.groups)
    if isinstance(visual, TextVisual):
        return (Headline(x=CANVAS_W / 2, y=_MID_Y, text=visual.headline, size=0.9),)
    raise LayoutError(f"no layout for visual {type(visual).__name__}")


def _bubble(text: str, name: str, side: int, portrait: str | None) -> tuple[Primitive, ...]:
    """A speech bubble: the speaker's name on top, the wrapped line below."""
    if not text or not name:
        raise LayoutError("a dialogue bubble needs both a line of text and a speaker name")
    if side not in (0, 1):
        raise LayoutError(f"bubble side must be 0 (left) or 1 (right), got {side}")
    lines = textwrap.wrap(text, width=BUBBLE_WRAP_CHARS) or [text]
    box_h = BUBBLE_NAME_H + len(lines) * BUBBLE_LINE_H + 0.5
    out: list[Primitive] = []
    if portrait is None:
        left = BUBBLE_EDGE if side == 0 else CANVAS_W - BUBBLE_EDGE - BUBBLE_W
    else:
        portrait_x = PORTRAIT_EDGE if side == 0 else CANVAS_W - PORTRAIT_EDGE - PORTRAIT_SIZE
        out.append(
            Picture(
                x=portrait_x,
                y=_MID_Y - PORTRAIT_SIZE / 2,
                w=PORTRAIT_SIZE,
                h=PORTRAIT_SIZE,
                path=portrait,
            )
        )
        if side == 0:
            left = portrait_x + PORTRAIT_SIZE + PORTRAIT_GAP
        else:
            left = portrait_x - PORTRAIT_GAP - BUBBLE_W
    top = _MID_Y + box_h / 2
    centre_x = left + BUBBLE_W / 2
    out.append(Box(x=left, y=top - box_h, w=BUBBLE_W, h=box_h, label=""))
    out.append(Headline(x=centre_x, y=top - 0.3, text=name, size=0.4))
    first_line_y = top - BUBBLE_NAME_H - 0.25 - BUBBLE_LINE_H / 2
    for index, line in enumerate(lines):
        out.append(
            Headline(
                x=centre_x,
                y=first_line_y - index * BUBBLE_LINE_H,
                text=line,
                size=0.34,
            )
        )
    return tuple(out)


def _flow(steps: list[str]) -> tuple[Primitive, ...]:
    gap = 0.8
    usable = CANVAS_W - 2 * _MARGIN
    box_w = min(3.2, (usable - gap * (len(steps) - 1)) / len(steps))
    box_h = 1.6
    total = box_w * len(steps) + gap * (len(steps) - 1)
    start_x = (CANVAS_W - total) / 2
    out: list[Primitive] = []
    for i, label in enumerate(steps):
        x = start_x + i * (box_w + gap)
        out.append(Box(x=x, y=_MID_Y - box_h / 2, w=box_w, h=box_h, label=label))
        if i < len(steps) - 1:
            out.append(
                Arrow(
                    x1=x + box_w + 0.1,
                    y1=_MID_Y,
                    x2=x + box_w + gap - 0.1,
                    y2=_MID_Y,
                )
            )
    return tuple(out)


def _checklist(items: list[str]) -> tuple[Primitive, ...]:
    row_gap = 0.25
    row_h = min(0.9, (CANVAS_H - 2 * _MARGIN - row_gap * (len(items) - 1)) / len(items))
    box_w = 9.0
    top = CANVAS_H - _MARGIN
    x = (CANVAS_W - box_w) / 2
    out: list[Primitive] = []
    for i, label in enumerate(items):
        y = top - (i + 1) * row_h - i * row_gap
        out.append(Box(x=x, y=y, w=box_w, h=row_h, label=label))
    return tuple(out)


def _roster(groups: list[str]) -> tuple[Primitive, ...]:
    gap = 0.6
    usable = CANVAS_W - 2 * _MARGIN
    box_w = min(3.6, (usable - gap * (len(groups) - 1)) / len(groups))
    box_h = 2.0
    total = box_w * len(groups) + gap * (len(groups) - 1)
    start_x = (CANVAS_W - total) / 2
    return tuple(
        Box(
            x=start_x + i * (box_w + gap),
            y=_MID_Y - box_h / 2,
            w=box_w,
            h=box_h,
            label=label,
        )
        for i, label in enumerate(groups)
    )
