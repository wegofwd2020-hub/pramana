"""The Blender lesson renderer: spec, layout, plan, assembly, scene build, CLI.

Mock data lives in ``tests/fixtures/blender_lesson``. Blender and Piper are
replaced by small fake executables that behave like the real ones for the
purposes of the pipeline (they write frames and a WAV file), so the whole path
runs in CI without a GPU or a voice model. Tests that need real ffmpeg are
skipped when it is not installed.
"""

from __future__ import annotations

import json
import shutil
import stat
import struct
import sys
import zlib
from itertools import pairwise
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.blender_lesson import cli
from scripts.blender_lesson.assemble import (
    AssemblyError,
    build_concat_list,
    build_scene_clip_cmd,
    build_srt,
    format_srt_time,
    run_tool,
)
from scripts.blender_lesson.layout import (
    CANVAS_H,
    CANVAS_W,
    Arrow,
    Box,
    Headline,
    LayoutError,
    layout_visual,
    primitive_from_dict,
    primitive_to_dict,
)
from scripts.blender_lesson.narrate import NarrationError, build_piper_cmd, probe_duration
from scripts.blender_lesson.plan import estimate_duration, plan_jobs, timeline
from scripts.blender_lesson.render_bpy import RenderError, build_scene
from scripts.blender_lesson.spec import (
    ChecklistVisual,
    FlowVisual,
    Lesson,
    SpecError,
    TextVisual,
    load_lesson,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "blender_lesson"
SAMPLE = FIXTURES / "sample_lesson.yaml"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")


def _write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


def _lesson_text(scenes: str, status: str = "approved") -> str:
    return f"id: T-1\ntitle: T\nclause: c\nstatus: {status}\nscenes:\n{scenes}"


# ---------------------------------------------------------------- spec


class TestSpec:
    def test_the_sample_fixture_loads(self) -> None:
        lesson, sha = load_lesson(SAMPLE)
        assert lesson.id == "TEST-LESSON-1"
        assert [s.id for s in lesson.scenes] == [1, 2, 3, 4]
        assert len(sha) == 64

    def test_status_defaults_to_draft(self, tmp_path: Path) -> None:
        text = _lesson_text(
            "  - id: 1\n    narration: hi\n    visual: {kind: text, headline: H}\n", status="draft"
        ).replace("status: draft\n", "")
        lesson, _ = load_lesson(_write(tmp_path, "s.yaml", text))
        assert lesson.status == "draft"

    def test_rejects_duplicate_scene_ids(self, tmp_path: Path) -> None:
        scenes = (
            "  - id: 1\n    narration: a\n    visual: {kind: text, headline: H}\n"
            "  - id: 1\n    narration: b\n    visual: {kind: text, headline: H}\n"
        )
        with pytest.raises(SpecError, match="unique"):
            load_lesson(_write(tmp_path, "s.yaml", _lesson_text(scenes)))

    def test_rejects_out_of_order_scene_ids(self, tmp_path: Path) -> None:
        scenes = (
            "  - id: 2\n    narration: a\n    visual: {kind: text, headline: H}\n"
            "  - id: 1\n    narration: b\n    visual: {kind: text, headline: H}\n"
        )
        with pytest.raises(SpecError, match="id order"):
            load_lesson(_write(tmp_path, "s.yaml", _lesson_text(scenes)))

    def test_rejects_an_unknown_visual_kind(self, tmp_path: Path) -> None:
        scenes = "  - id: 1\n    narration: a\n    visual: {kind: hologram}\n"
        with pytest.raises(SpecError, match="does not validate"):
            load_lesson(_write(tmp_path, "s.yaml", _lesson_text(scenes)))

    def test_rejects_an_unknown_field(self, tmp_path: Path) -> None:
        scenes = (
            "  - id: 1\n    narration: a\n    visual: {kind: text, headline: H}\n    music: loud\n"
        )
        with pytest.raises(SpecError, match="does not validate"):
            load_lesson(_write(tmp_path, "s.yaml", _lesson_text(scenes)))

    def test_rejects_an_overlong_label(self, tmp_path: Path) -> None:
        scenes = (
            "  - id: 1\n    narration: a\n    visual: {kind: flow, steps: ['"
            + "x" * 41
            + "', 'b']}\n"
        )
        with pytest.raises(SpecError, match="does not validate"):
            load_lesson(_write(tmp_path, "s.yaml", _lesson_text(scenes)))

    def test_rejects_malformed_yaml(self, tmp_path: Path) -> None:
        with pytest.raises(SpecError, match="not valid YAML"):
            load_lesson(_write(tmp_path, "s.yaml", "id: [unclosed"))

    def test_missing_file_is_a_spec_error(self, tmp_path: Path) -> None:
        with pytest.raises(SpecError, match="cannot read"):
            load_lesson(tmp_path / "nope.yaml")


# ---------------------------------------------------------------- layout


class TestLayout:
    def test_flow_has_a_box_per_step_and_an_arrow_between(self) -> None:
        prims = layout_visual(FlowVisual(kind="flow", steps=["A", "B", "C"]))
        boxes = [p for p in prims if isinstance(p, Box)]
        arrows = [p for p in prims if isinstance(p, Arrow)]
        assert [b.label for b in boxes] == ["A", "B", "C"]
        assert len(arrows) == 2

    def test_every_box_stays_on_the_canvas(self) -> None:
        for visual in (
            FlowVisual(kind="flow", steps=["one", "two", "three", "four", "five", "six"]),
            ChecklistVisual(kind="checklist", items=[f"item {i}" for i in range(8)]),
        ):
            for box in (p for p in layout_visual(visual) if isinstance(p, Box)):
                assert box.x >= 0 and box.x + box.w <= CANVAS_W
                assert box.y >= 0 and box.y + box.h <= CANVAS_H

    def test_checklist_rows_do_not_overlap(self) -> None:
        prims = [
            p
            for p in layout_visual(ChecklistVisual(kind="checklist", items=list("abcdefgh")))
            if isinstance(p, Box)
        ]
        ordered = sorted(prims, key=lambda b: b.y, reverse=True)
        for upper, lower in pairwise(ordered):
            assert lower.y + lower.h <= upper.y

    def test_text_becomes_a_centred_headline(self) -> None:
        (prim,) = layout_visual(TextVisual(kind="text", headline="Hello"))
        assert isinstance(prim, Headline)
        assert prim.x == CANVAS_W / 2 and prim.y == CANVAS_H / 2

    def test_layout_is_deterministic(self) -> None:
        visual = FlowVisual(kind="flow", steps=["a", "b"])
        assert layout_visual(visual) == layout_visual(visual)

    def test_primitives_round_trip_through_the_job_form(self) -> None:
        for prim in layout_visual(FlowVisual(kind="flow", steps=["a", "b"])):
            assert primitive_from_dict(primitive_to_dict(prim)) == prim

    def test_an_unknown_primitive_type_is_rejected(self) -> None:
        with pytest.raises(LayoutError):
            primitive_from_dict({"type": "sphere"})


# ---------------------------------------------------------------- plan


class TestPlan:
    def _lesson(self) -> Lesson:
        lesson, _ = load_lesson(SAMPLE)
        return lesson

    def test_frames_are_duration_times_fps_rounded_up(self, tmp_path: Path) -> None:
        jobs = plan_jobs(self._lesson(), tmp_path, fps=24, durations={1: 2.01})
        assert jobs[0].frames == 49

    def test_unmeasured_scenes_fall_back_to_an_estimate(self, tmp_path: Path) -> None:
        jobs = plan_jobs(self._lesson(), tmp_path, fps=24, durations={1: 3.0})
        assert jobs[0].duration_s == 3.0
        assert jobs[1].duration_s == estimate_duration(self._lesson().scenes[1].narration)

    def test_estimate_has_a_floor(self) -> None:
        assert estimate_duration("Hi.") == 2.0

    def test_estimate_scales_with_length(self) -> None:
        long_line = " ".join(["word"] * 50)
        assert estimate_duration(long_line) == pytest.approx(50 / 2.5)

    def test_fps_must_be_positive(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="positive"):
            plan_jobs(self._lesson(), tmp_path, fps=0)

    def test_each_job_writes_frames_under_its_own_scene(self, tmp_path: Path) -> None:
        jobs = plan_jobs(self._lesson(), tmp_path, fps=24)
        assert jobs[0].frames_dir == tmp_path / "scene-01" / "frames"
        assert len({j.frames_dir for j in jobs}) == len(jobs)

    def test_timeline_is_cumulative(self, tmp_path: Path) -> None:
        jobs = plan_jobs(self._lesson(), tmp_path, fps=24, durations={1: 2.0, 2: 3.5})
        spans = timeline(jobs)
        assert spans[0][:2] == (0.0, 2.0)
        assert spans[1][0] == 2.0 and spans[1][1] == pytest.approx(5.5)


# ---------------------------------------------------------------- assemble


class TestAssemble:
    def test_srt_timestamps_use_the_comma_millisecond_form(self) -> None:
        assert format_srt_time(0) == "00:00:00,000"
        assert format_srt_time(3723.456) == "01:02:03,456"

    def test_negative_time_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_srt_time(-1)

    def test_srt_numbers_and_orders_each_cue(self) -> None:
        srt = build_srt([(0.0, 2.0, "First."), (2.0, 4.5, "Second.")])
        assert srt.startswith("1\n00:00:00,000 --> 00:00:02,000\nFirst.\n")
        assert "2\n00:00:02,000 --> 00:00:04,500\nSecond.\n" in srt

    def test_scene_clip_starts_frame_numbering_at_one(self, tmp_path: Path) -> None:
        cmd = build_scene_clip_cmd(
            frames_dir=tmp_path, fps=24, audio=tmp_path / "a.wav", out_clip=tmp_path / "c.mp4"
        )
        assert cmd[cmd.index("-start_number") + 1] == "1"
        assert "-shortest" in cmd

    def test_concat_list_is_in_order(self, tmp_path: Path) -> None:
        text = build_concat_list([tmp_path / "a.mp4", tmp_path / "b.mp4"])
        assert text.index("a.mp4") < text.index("b.mp4")
        assert text.count("file '") == 2

    def test_a_missing_tool_is_an_assembly_error(self) -> None:
        with pytest.raises(AssemblyError, match="not installed"):
            run_tool(["definitely-not-a-real-binary-xyz"])

    def test_a_non_zero_exit_is_an_assembly_error(self) -> None:
        with pytest.raises(AssemblyError, match="exited 3"):
            run_tool([sys.executable, "-c", "import sys; sys.exit(3)"])


# ---------------------------------------------------------------- narrate


class TestNarrate:
    def test_piper_is_invoked_as_a_module_with_the_voice_path(self, tmp_path: Path) -> None:
        model = tmp_path / "en_US-lessac-medium.onnx"
        cmd = build_piper_cmd("python3", model, tmp_path / "o.wav")
        assert cmd[:3] == ["python3", "-m", "piper"]
        assert cmd[cmd.index("-m", 2) + 1] == str(model)
        assert cmd[cmd.index("-f") + 1] == str(tmp_path / "o.wav")

    def test_the_text_never_appears_on_the_command_line(self, tmp_path: Path) -> None:
        # Narration is fed on stdin, so a line that looks like an option cannot be parsed as one.
        cmd = build_piper_cmd("python3", tmp_path / "v.onnx", tmp_path / "o.wav")
        assert "--" not in cmd
        assert not any("-not a flag" in part for part in cmd)

    def test_a_multi_line_narration_is_rejected_by_the_spec(self) -> None:
        from pydantic import ValidationError

        from scripts.blender_lesson.spec import Scene

        with pytest.raises(ValidationError, match="single line"):
            Scene.model_validate(
                {
                    "id": 1,
                    "narration": "First line.\nSecond line.",
                    "visual": {"kind": "text", "headline": "Hi"},
                }
            )

    def test_a_missing_voice_model_is_a_narration_error(self, tmp_path: Path) -> None:
        from scripts.blender_lesson.narrate import synthesize

        with pytest.raises(NarrationError, match="voice model not found"):
            synthesize("hi", tmp_path / "o.wav", python_bin="python3", model=tmp_path / "x.onnx")

    def test_a_voice_without_its_json_config_is_a_narration_error(self, tmp_path: Path) -> None:
        from scripts.blender_lesson.narrate import synthesize

        model = tmp_path / "v.onnx"
        model.write_bytes(b"model")
        with pytest.raises(NarrationError, match="config not found"):
            synthesize("hi", tmp_path / "o.wav", python_bin="python3", model=model)

    def test_probing_a_missing_file_is_a_narration_error(self, tmp_path: Path) -> None:
        with pytest.raises(NarrationError):
            probe_duration(tmp_path / "missing.wav", ffprobe="definitely-not-a-real-binary-xyz")


# ---------------------------------------------------------------- render_bpy


class TestRenderBpy:
    def _job(self, primitives: list[dict[str, object]]) -> dict[str, object]:
        return {
            "scene_id": 1,
            "fps": 24,
            "frames": 10,
            "frames_dir": "unused",
            "resolution": [1280, 720],
            "primitives": primitives,
        }

    def test_each_box_becomes_a_quad_and_a_label(self, tmp_path: Path) -> None:
        bpy = MagicMock()
        job = self._job(
            [
                {"type": "box", "x": 1.0, "y": 1.0, "w": 2.0, "h": 1.0, "label": "A"},
                {"type": "box", "x": 4.0, "y": 1.0, "w": 2.0, "h": 1.0, "label": "B"},
            ]
        )
        job["frames_dir"] = str(tmp_path / "frames")
        primitives = build_scene(bpy, job)
        assert len(primitives) == 2
        assert bpy.data.meshes.new.call_count == 2  # two boxes, no arrows
        labels = [c.kwargs.get("type") for c in bpy.data.curves.new.call_args_list]
        assert labels == ["FONT", "FONT"]

    def test_the_camera_is_orthographic_and_set_active(self, tmp_path: Path) -> None:
        bpy = MagicMock()
        job = self._job([])
        job["frames_dir"] = str(tmp_path / "frames")
        build_scene(bpy, job)
        cam_data = bpy.data.cameras.new.return_value
        assert cam_data.type == "ORTHO"
        assert cam_data.ortho_scale == CANVAS_W

    def test_the_engine_and_frame_range_are_set(self, tmp_path: Path) -> None:
        bpy = MagicMock()
        job = self._job([])
        job["frames_dir"] = str(tmp_path / "frames")
        build_scene(bpy, job)
        scene = bpy.context.scene
        assert scene.render.engine == "BLENDER_EEVEE"
        assert scene.frame_end == 10

    def test_a_job_without_primitives_is_rejected(self) -> None:
        with pytest.raises(RenderError, match="primitives"):
            build_scene(
                MagicMock(), {"frames_dir": "x", "resolution": [1, 1], "fps": 1, "frames": 1}
            )


# ---------------------------------------------------------------- CLI


def _png(width: int, height: int) -> bytes:
    """A valid solid-white PNG, written by hand so the fake Blender needs no image library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


FAKE_BLENDER = """#!{python}
import json, pathlib, sys
argv = sys.argv
if "--version" in argv:
    print("Blender 4.0.2 (fake, test double)")
    sys.exit(0)
if {fail!r}:
    sys.exit(7)
job = json.loads(pathlib.Path(argv[argv.index("--") + 1]).read_text())
frames = pathlib.Path(job["frames_dir"])
frames.mkdir(parents=True, exist_ok=True)
png = {png!r}
for i in range(1, job["frames"] + 1):
    (frames / f"frame_{{i:04d}}.png").write_bytes(png)
"""

FAKE_PYTHON = """#!{python}
# Stands in for `python3` with piper-tts installed. Only `-m piper` is handled.
import sys, wave
argv = sys.argv[1:]
if argv[:2] != ["-m", "piper"]:
    sys.exit(0)
out = argv[argv.index("-f") + 1]
text = sys.stdin.read()
seconds = max(0.5, len(text.split()) / 2.5)
rate = 8000
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(b"\\x00\\x00" * int(seconds * rate))
"""


def _fake_tool(tmp: Path, name: str, body: str) -> str:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


@pytest.fixture
def fakes(tmp_path: Path) -> dict[str, str]:
    png = _png(2, 2)
    blender = _fake_tool(
        tmp_path, "fake-blender", FAKE_BLENDER.format(python=sys.executable, fail=False, png=png)
    )
    python = _fake_tool(tmp_path, "fake-python", FAKE_PYTHON.format(python=sys.executable))
    model = tmp_path / "en_US-test-medium.onnx"
    model.write_bytes(b"not a real model; the fake piper ignores it")
    (tmp_path / "en_US-test-medium.onnx.json").write_text("{}", encoding="utf-8")
    return {"blender": blender, "python": python, "model": str(model)}


class TestCli:
    def test_dry_run_prints_the_plan_and_runs_no_tools(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli.main([str(SAMPLE), "--out-dir", str(tmp_path / "out"), "--dry-run"])
        assert code == 0
        plan = json.loads(capsys.readouterr().out)
        assert plan["lesson"] == "TEST-LESSON-1"
        assert len(plan["scenes"]) == 4
        assert not (tmp_path / "out").exists()

    def test_a_draft_is_refused_without_the_override(self, tmp_path: Path) -> None:
        spec = _write(
            tmp_path,
            "draft.yaml",
            _lesson_text(
                "  - id: 1\n    narration: a\n    visual: {kind: text, headline: H}\n",
                status="draft",
            ),
        )
        code = cli.main([str(spec), "--out-dir", str(tmp_path / "out")])
        assert code == cli.EXIT_SPEC

    def test_an_invalid_spec_exits_with_the_spec_code(self, tmp_path: Path) -> None:
        spec = _write(tmp_path, "bad.yaml", "id: [oops")
        assert cli.main([str(spec), "--out-dir", str(tmp_path / "out")]) == cli.EXIT_SPEC

    def test_a_missing_piper_model_is_a_narration_failure(
        self, tmp_path: Path, fakes: dict[str, str]
    ) -> None:
        code = cli.main(
            [str(SAMPLE), "--out-dir", str(tmp_path / "out"), "--blender", fakes["blender"]]
        )
        assert code == cli.EXIT_NARRATION

    @needs_ffmpeg
    def test_a_full_run_produces_video_subtitles_and_provenance(
        self, tmp_path: Path, fakes: dict[str, str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "out"
        code = cli.main(
            [
                str(SAMPLE),
                "--out-dir",
                str(out),
                "--fps",
                "4",
                "--blender",
                fakes["blender"],
                "--python",
                fakes["python"],
                "--piper-model",
                fakes["model"],
            ]
        )
        assert code == cli.EXIT_OK, capsys.readouterr().err
        assert (out / "lesson.mp4").stat().st_size > 0
        assert "-->" in (out / "lesson.srt").read_text()
        assert (out / "transcript.txt").read_text().splitlines()[0] == "Every control has an owner."

        prov = json.loads((out / "provenance.json").read_text())
        assert prov["lesson"] == "TEST-LESSON-1"
        assert prov["blender"].startswith("Blender 4.0.2")
        assert len(prov["spec_sha256"]) == 64
        assert len(prov["video_sha256"]) == 64
        assert set(prov["scene_durations_s"]) == {"1", "2", "3", "4"}

    @needs_ffmpeg
    def test_a_blender_failure_exits_with_the_render_code(
        self, tmp_path: Path, fakes: dict[str, str]
    ) -> None:
        spec = _write(
            tmp_path,
            "fail.yaml",
            _lesson_text(
                "  - id: 1\n    narration: this will fail\n    visual: {kind: text, headline: H}\n"
            ),
        )
        failing = _fake_tool(
            tmp_path,
            "failing-blender",
            FAKE_BLENDER.format(python=sys.executable, fail=True, png=_png(2, 2)),
        )
        code = cli.main(
            [
                str(spec),
                "--out-dir",
                str(tmp_path / "out"),
                "--blender",
                failing,
                "--python",
                fakes["python"],
                "--piper-model",
                fakes["model"],
            ]
        )
        assert code == cli.EXIT_RENDER
