"""Lesson spec: the validated input to the Blender lesson renderer.

A spec is one lesson: a title, the framework clause it teaches, and an ordered
list of scenes. Each scene carries the narration line the learner reads and one
visual, drawn from a fixed set of kinds. The visuals are deliberately simple —
boxes, arrows and text in a font — because a generated image can depict nothing
in particular, and the fidelity gate exists to catch exactly that.

The ``status`` field mirrors the first of the two gates. A ``draft`` script is
rendered only on an explicit override, so an unapproved script cannot reach a
learner by accident.

Errors surface as :class:`SpecError` with a message a human can act on.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MAX_NARRATION_CHARS = 400
MAX_LABEL_CHARS = 40
#: A speech bubble holds about five wrapped lines; longer text overflows the frame.
MAX_BUBBLE_CHARS = 160
#: The layout puts the first speaker on the left and the second on the right.
MAX_CAST = 2


class SpecError(Exception):
    """The spec file is unreadable or does not validate."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FlowVisual(_Strict):
    """Boxes joined by arrows, read left to right."""

    kind: Literal["flow"]
    steps: list[Annotated[str, Field(min_length=1, max_length=MAX_LABEL_CHARS)]] = Field(
        min_length=2, max_length=6
    )


class ChecklistVisual(_Strict):
    """A stacked list of items, each with a box to tick."""

    kind: Literal["checklist"]
    items: list[Annotated[str, Field(min_length=1, max_length=MAX_LABEL_CHARS)]] = Field(
        min_length=1, max_length=8
    )


class RosterVisual(_Strict):
    """A row of groups, for "who is in scope"."""

    kind: Literal["roster"]
    groups: list[Annotated[str, Field(min_length=1, max_length=MAX_LABEL_CHARS)]] = Field(
        min_length=1, max_length=6
    )


class TextVisual(_Strict):
    """A single headline on a plain background."""

    kind: Literal["text"]
    headline: str = Field(min_length=1, max_length=60)


class DialogueVisual(_Strict):
    """A speech bubble from one cast member. The scene's narration is the bubble text."""

    kind: Literal["dialogue"]
    speaker: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,15}$")


Visual = Annotated[
    FlowVisual | ChecklistVisual | RosterVisual | TextVisual | DialogueVisual,
    Field(discriminator="kind"),
]


class Speaker(_Strict):
    """A cast member: the name shown in the bubble and the Piper voice that speaks their lines."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,15}$")
    name: str = Field(min_length=1, max_length=40)
    voice: str = Field(
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Piper voice name, for example en_US-ryan-high",
    )


class Scene(_Strict):
    id: int = Field(ge=1)
    narration: str = Field(min_length=1, max_length=MAX_NARRATION_CHARS)
    visual: Visual

    @field_validator("narration")
    @classmethod
    def _single_line(cls, text: str) -> str:
        # Piper synthesises one line at a time; a line break would split the scene.
        if "\n" in text or "\r" in text:
            raise ValueError("narration must be a single line")
        return text


class Lesson(_Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=120)
    clause: str = Field(min_length=1, description="Framework anchor the lesson teaches")
    status: Literal["draft", "approved"] = "draft"
    cast: list[Speaker] = Field(default_factory=list, max_length=MAX_CAST)
    scenes: list[Scene] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _dialogue_refers_to_the_cast(self) -> Lesson:
        ids = [speaker.id for speaker in self.cast]
        if len(set(ids)) != len(ids):
            raise ValueError(f"cast ids must be unique, got {ids}")
        for scene in self.scenes:
            if not isinstance(scene.visual, DialogueVisual):
                continue
            if scene.visual.speaker not in ids:
                raise ValueError(
                    f"scene {scene.id}: speaker {scene.visual.speaker!r} is not in the cast {ids}"
                )
            if len(scene.narration) > MAX_BUBBLE_CHARS:
                raise ValueError(
                    f"scene {scene.id}: a dialogue line is {len(scene.narration)} characters; "
                    f"the bubble holds {MAX_BUBBLE_CHARS}"
                )
        return self

    @field_validator("scenes")
    @classmethod
    def _scene_ids_are_ordered_and_unique(cls, scenes: list[Scene]) -> list[Scene]:
        ids = [scene.id for scene in scenes]
        if len(set(ids)) != len(ids):
            raise ValueError(f"scene ids must be unique, got {ids}")
        if ids != sorted(ids):
            raise ValueError(f"scenes must be listed in id order, got {ids}")
        return scenes


def load_lesson(path: Path) -> tuple[Lesson, str]:
    """Read and validate a lesson spec.

    Returns the validated lesson and the SHA-256 of the raw file, which the
    provenance record uses to pin the exact script that was rendered.

    Raises:
        SpecError: the file is missing, is not YAML, or does not validate.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read spec {path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SpecError(f"{path} is not valid YAML: {exc}") from exc

    try:
        lesson = Lesson.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise SpecError(f"{path} does not validate: {details}") from exc

    return lesson, hashlib.sha256(raw).hexdigest()
