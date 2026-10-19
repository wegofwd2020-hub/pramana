"""Blender-side renderer. Runs inside Blender, once per scene job.

Invoked as::

    blender -b --python scripts/blender_lesson/render_bpy.py -- job.json

It reads one scene's job file, builds the primitives into a fresh scene and
renders PNG frames. Only :func:`main` needs ``bpy``; the module imports without
it, so the scene-building functions can be exercised with a stub.

The scene is deliberately plain: a white world, one orthographic camera looking
straight down the canvas, one sun, and flat-coloured quads and text. There is
no randomness, so the same job always renders the same frames.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Blender runs this file as a script, so the repo root is not on sys.path yet.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.blender_lesson.primitives import (  # noqa: E402 - needs the path set above
    CANVAS_H,
    CANVAS_W,
    Arrow,
    Box,
    Headline,
    Picture,
    Primitive,
    primitive_from_dict,
)

ENGINE = "BLENDER_EEVEE"
BOX_RGBA = (0.16, 0.36, 0.62, 1.0)
ARROW_RGBA = (0.35, 0.35, 0.35, 1.0)
TEXT_RGBA = (0.08, 0.08, 0.10, 1.0)
LABEL_RGBA = (1.0, 1.0, 1.0, 1.0)
#: A box with no label is a speech bubble: a light fill, so dark dialogue text reads clearly.
BUBBLE_RGBA = (0.98, 0.98, 0.97, 1.0)
LABEL_SIZE = 0.42
#: Pictures sit behind boxes and text, which are at z = 0 and above.
PICTURE_Z = -0.05


class RenderError(RuntimeError):
    """The job file is unusable, or the scene could not be built."""


def _clear(bpy: Any) -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _material(bpy: Any, name: str, rgba: tuple[float, float, float, float]) -> Any:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RenderError("material has no Principled BSDF node; cannot set colour")
    bsdf.inputs["Base Color"].default_value = rgba
    return mat


def _link(bpy: Any, obj: Any) -> None:
    bpy.context.scene.collection.objects.link(obj)


def _quad(
    bpy: Any,
    name: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    z: float,
    material: Any,
) -> None:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    _link(bpy, obj)


def _text(bpy: Any, name: str, text: str, x: float, y: float, size: float, material: Any) -> None:
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(name, curve)
    obj.location = (x, y, 0.02)
    obj.data.materials.append(material)
    _link(bpy, obj)


def _picture(
    bpy: Any,
    name: str,
    path: str,
    box: tuple[float, float, float, float],
) -> None:
    """A PNG on a quad. Emission carries the image, so lighting does not darken it."""
    x0, y0, x1, y1 = box
    try:
        image = bpy.data.images.load(path, check_existing=True)
    except RuntimeError as exc:
        raise RenderError(f"cannot load picture {path}: {exc}") from exc
    mat = bpy.data.materials.new(f"{name}-mat")
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RenderError("material has no Principled BSDF node; cannot show a picture")
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    tree.links.new(texture.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(x0, y0, PICTURE_Z), (x1, y0, PICTURE_Z), (x1, y1, PICTURE_Z), (x0, y1, PICTURE_Z)],
        [],
        [(0, 1, 2, 3)],
    )
    uv = mesh.uv_layers.new(name="UVMap")
    for loop_index, corner in enumerate(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        uv.data[loop_index].uv = corner
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat)
    _link(bpy, obj)


def _add_primitive(bpy: Any, index: int, primitive: Primitive, mats: dict[str, Any]) -> None:
    name = f"p{index:03d}"
    if isinstance(primitive, Box):
        _quad(
            bpy,
            name,
            primitive.x,
            primitive.y,
            primitive.x + primitive.w,
            primitive.y + primitive.h,
            0.0,
            mats["box"] if primitive.label else mats["bubble"],
        )
        # Speech bubbles are boxes with no label; their text is drawn as headlines.
        if primitive.label:
            _text(
                bpy,
                f"{name}-label",
                primitive.label,
                primitive.x + primitive.w / 2,
                primitive.y + primitive.h / 2,
                LABEL_SIZE,
                mats["label"],
            )
    elif isinstance(primitive, Arrow):
        thickness = 0.06
        _quad(
            bpy,
            name,
            primitive.x1,
            primitive.y1 - thickness,
            primitive.x2,
            primitive.y2 + thickness,
            0.0,
            mats["arrow"],
        )
    elif isinstance(primitive, Picture):
        _picture(
            bpy,
            name,
            primitive.path,
            (primitive.x, primitive.y, primitive.x + primitive.w, primitive.y + primitive.h),
        )
    elif isinstance(primitive, Headline):
        _text(bpy, name, primitive.text, primitive.x, primitive.y, primitive.size, mats["text"])
    else:  # pragma: no cover - the union is closed; this guards a future kind
        raise RenderError(f"cannot draw {type(primitive).__name__}")


def _camera_and_light(bpy: Any) -> None:
    cam_data = bpy.data.cameras.new("camera")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = CANVAS_W
    cam = bpy.data.objects.new("camera", cam_data)
    cam.location = (CANVAS_W / 2, CANVAS_H / 2, 10.0)
    _link(bpy, cam)
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.location = (CANVAS_W / 2, CANVAS_H / 2, 8.0)
    _link(bpy, sun)


def _render_settings(bpy: Any, job: dict[str, Any]) -> None:
    scene = bpy.context.scene
    width, height = job["resolution"]
    scene.render.engine = ENGINE
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.resolution_percentage = 100
    scene.render.fps = int(job["fps"])
    scene.frame_start = 1
    scene.frame_end = int(job["frames"])
    scene.render.image_settings.file_format = "PNG"
    frames_dir = Path(job["frames_dir"])
    frames_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frames_dir / "frame_")
    world = bpy.data.worlds.new("world")
    world.use_nodes = False
    world.color = (1.0, 1.0, 1.0)
    scene.world = world


def build_scene(bpy: Any, job: dict[str, Any]) -> list[Primitive]:
    """Populate the open Blender scene from one job. Returns what was drawn."""
    if not isinstance(job.get("primitives"), list):
        raise RenderError("job has no primitives list")
    primitives = [primitive_from_dict(p) for p in job["primitives"]]
    _clear(bpy)
    mats = {
        "box": _material(bpy, "box", BOX_RGBA),
        "arrow": _material(bpy, "arrow", ARROW_RGBA),
        "text": _material(bpy, "text", TEXT_RGBA),
        "label": _material(bpy, "label", LABEL_RGBA),
        "bubble": _material(bpy, "bubble", BUBBLE_RGBA),
    }
    for index, primitive in enumerate(primitives):
        _add_primitive(bpy, index, primitive, mats)
    _camera_and_light(bpy)
    _render_settings(bpy, job)
    return primitives


def _job_path(argv: list[str]) -> Path:
    if "--" not in argv:
        raise RenderError("usage: blender -b --python render_bpy.py -- job.json")
    rest = argv[argv.index("--") + 1 :]
    if len(rest) != 1:
        raise RenderError("expected exactly one job file after '--'")
    return Path(rest[0])


def main(argv: list[str]) -> int:
    """Render one job. Returns a process exit code."""
    import bpy  # type: ignore[import-not-found]  # only exists inside Blender

    try:
        job = json.loads(_job_path(argv).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, RenderError) as exc:
        print(f"render_bpy: cannot read job: {exc}", file=sys.stderr)
        return 2
    try:
        build_scene(bpy, job)
        bpy.ops.render.render(animation=True)
    except RenderError as exc:
        print(f"render_bpy: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
