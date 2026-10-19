"""Positioned primitives: the shapes a visual is reduced to before Blender draws them.

This module has no third-party imports on purpose. Blender's bundled Python does
not ship ``pydantic`` or ``pyyaml``, and ``render_bpy`` imports this module inside
Blender, so anything heavier would break the render.

Coordinates are in canvas units, origin at the bottom-left, y pointing up. The
canvas is 16 units wide and 9 units high, which matches a 16:9 frame.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CANVAS_W = 16.0
CANVAS_H = 9.0


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float
    label: str


@dataclass(frozen=True)
class Arrow:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class Headline:
    x: float
    y: float
    text: str
    size: float


@dataclass(frozen=True)
class Picture:
    """A PNG drawn as a flat image over a rectangle. ``path`` is absolute in the job file."""

    x: float
    y: float
    w: float
    h: float
    path: str


Primitive = Box | Arrow | Headline | Picture


class LayoutError(ValueError):
    """A visual cannot be laid out on the canvas."""


def primitive_to_dict(primitive: Primitive) -> dict[str, Any]:
    """Serialise a primitive with a ``type`` tag, for the job file."""
    tag = {Box: "box", Arrow: "arrow", Headline: "headline", Picture: "picture"}[type(primitive)]
    return {"type": tag, **asdict(primitive)}


def primitive_from_dict(data: dict[str, Any]) -> Primitive:
    """Rebuild a primitive from its job-file form. Inverse of ``primitive_to_dict``."""
    body = {k: v for k, v in data.items() if k != "type"}
    kind = data.get("type")
    if kind == "box":
        return Box(**body)
    if kind == "arrow":
        return Arrow(**body)
    if kind == "headline":
        return Headline(**body)
    if kind == "picture":
        return Picture(**body)
    raise LayoutError(f"unknown primitive type {kind!r}")
