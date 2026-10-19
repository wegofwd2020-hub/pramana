"""Turn a visual into positioned primitives on a 16 x 9 unit canvas.

This module is pure arithmetic. It knows nothing about Blender, so the layout can
be unit-tested without it. The Blender side (``render_bpy``) only translates the
primitives into scene objects.

Coordinates are in canvas units, origin at the bottom-left, y pointing up. The
canvas is 16 units wide and 9 units high, which matches a 16:9 frame.
"""

from __future__ import annotations

from scripts.blender_lesson.primitives import (
    CANVAS_H,
    CANVAS_W,
    Arrow,
    Box,
    Headline,
    LayoutError,
    Primitive,
)
from scripts.blender_lesson.spec import (
    ChecklistVisual,
    FlowVisual,
    RosterVisual,
    TextVisual,
    Visual,
)

_MARGIN = 1.0
_MID_Y = CANVAS_H / 2


def layout_visual(visual: Visual) -> tuple[Primitive, ...]:
    """Return the primitives for one scene's visual, deterministically."""
    if isinstance(visual, FlowVisual):
        return _flow(visual.steps)
    if isinstance(visual, ChecklistVisual):
        return _checklist(visual.items)
    if isinstance(visual, RosterVisual):
        return _roster(visual.groups)
    if isinstance(visual, TextVisual):
        return (Headline(x=CANVAS_W / 2, y=_MID_Y, text=visual.headline, size=0.9),)
    raise LayoutError(f"no layout for visual {type(visual).__name__}")


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
