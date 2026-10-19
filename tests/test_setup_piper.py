"""Tests for the Piper setup script. No network and no real Piper: every external call is mocked."""

from __future__ import annotations

import io
import subprocess
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from scripts.blender_lesson import setup_piper as sp

# Mock data: a voice name and the bytes a fake download returns.
SAMPLE_VOICE = "en_US-lessac-medium"
SAMPLE_BYTES = b"not really an onnx model, but non-empty"


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@pytest.fixture
def fake_urlopen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace urlopen with a fake that serves SAMPLE_BYTES and records each URL."""
    requested: list[str] = []

    def _open(url: str, timeout: float) -> _FakeResponse:
        requested.append(url)
        return _FakeResponse(SAMPLE_BYTES)

    monkeypatch.setattr(sp.urllib.request, "urlopen", _open)
    return requested


class TestVoiceFiles:
    def test_maps_a_voice_name_to_its_collection_path(self) -> None:
        files = sp.voice_files(SAMPLE_VOICE)
        base = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/"
        assert files.model_url == base + "en_US-lessac-medium.onnx"
        assert files.config_url == base + "en_US-lessac-medium.onnx.json"
        assert files.model_filename == "en_US-lessac-medium.onnx"
        assert files.config_filename == "en_US-lessac-medium.onnx.json"

    def test_a_british_voice_uses_its_own_language_folder(self) -> None:
        files = sp.voice_files("en_GB-alba-medium")
        assert "/en/en_GB/alba/medium/" in files.model_url

    @pytest.mark.parametrize(
        "bad", ["lessac", "en_US-lessac", "EN_US-lessac-medium", "en_US-lessac-huge", ""]
    )
    def test_a_malformed_name_is_a_setup_error(self, bad: str) -> None:
        with pytest.raises(sp.SetupError, match="not of the form"):
            sp.voice_files(bad)


class TestDownload:
    def test_writes_the_file_and_leaves_no_partial(
        self, tmp_path: Path, fake_urlopen: list[str]
    ) -> None:
        dest = sp.download("https://example.test/v.onnx", tmp_path / "v.onnx")
        assert dest.read_bytes() == SAMPLE_BYTES
        assert not (tmp_path / "v.onnx.part").exists()
        assert fake_urlopen == ["https://example.test/v.onnx"]

    def test_an_existing_file_is_not_fetched_again(
        self, tmp_path: Path, fake_urlopen: list[str]
    ) -> None:
        existing = tmp_path / "v.onnx"
        existing.write_bytes(b"already here")
        sp.download("https://example.test/v.onnx", existing)
        assert fake_urlopen == []
        assert existing.read_bytes() == b"already here"

    def test_an_http_error_is_a_setup_error_and_cleans_up(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _404(url: str, timeout: float) -> None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr(sp.urllib.request, "urlopen", _404)
        with pytest.raises(sp.SetupError, match="HTTP 404"):
            sp.download("https://example.test/missing.onnx", tmp_path / "missing.onnx")
        assert not (tmp_path / "missing.onnx").exists()
        assert not (tmp_path / "missing.onnx.part").exists()

    def test_a_network_error_is_a_setup_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _down(url: str, timeout: float) -> None:
            raise urllib.error.URLError("proxy refused")

        monkeypatch.setattr(sp.urllib.request, "urlopen", _down)
        with pytest.raises(sp.SetupError, match="proxy refused"):
            sp.download("https://example.test/v.onnx", tmp_path / "v.onnx")


class TestInstallVoice:
    def test_fetches_both_files_side_by_side(self, tmp_path: Path, fake_urlopen: list[str]) -> None:
        model = sp.install_voice(sp.voice_files(SAMPLE_VOICE), tmp_path)
        assert model == tmp_path / "en_US-lessac-medium.onnx"
        assert (tmp_path / "en_US-lessac-medium.onnx.json").is_file()
        assert len(fake_urlopen) == 2


class TestMissingTools:
    def test_reports_only_the_tools_not_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        present = {"blender": "/usr/bin/blender", "ffmpeg": "/usr/bin/ffmpeg"}
        monkeypatch.setattr(sp.shutil, "which", lambda tool: present.get(tool))
        assert sp.missing_tools() == ["ffprobe"]

    def test_nothing_missing_when_all_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sp.shutil, "which", lambda tool: f"/usr/bin/{tool}")
        assert sp.missing_tools() == []


class TestVerifySynthesis:
    def test_returns_the_duration_of_the_written_wav(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "piper-python":
                out = Path(cmd[cmd.index("-f") + 1])
                out.write_bytes(b"RIFF")
                assert kwargs["input"] == sp.CHECK_PHRASE
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "1.75\n", "")

        monkeypatch.setattr(sp.subprocess, "run", _fake_run)
        seconds = sp.verify_synthesis(
            Path("piper-python"), tmp_path / "v.onnx", tmp_path / "check.wav"
        )
        assert seconds == pytest.approx(1.75)

    def test_a_piper_failure_reports_its_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "ValueError: bad config")

        monkeypatch.setattr(sp.subprocess, "run", _fail)
        with pytest.raises(sp.SetupError, match="bad config"):
            sp.verify_synthesis(Path("piper-python"), tmp_path / "v.onnx", tmp_path / "check.wav")

    def test_a_zero_length_wav_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[0] == "piper-python":
                Path(cmd[cmd.index("-f") + 1]).write_bytes(b"RIFF")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "0.0\n", "")

        monkeypatch.setattr(sp.subprocess, "run", _fake_run)
        with pytest.raises(sp.SetupError, match="non-positive"):
            sp.verify_synthesis(Path("piper-python"), tmp_path / "v.onnx", tmp_path / "check.wav")


class TestCreateVenvAndInstall:
    def test_an_existing_venv_is_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        python = tmp_path / "venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("")
        calls: list[list[str]] = []
        monkeypatch.setattr(sp, "_run", lambda cmd, step: calls.append(cmd) or "")
        assert sp.create_venv(tmp_path / "venv") == python
        assert calls == []

    def test_a_failed_pip_install_is_a_setup_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fail(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "no matching distribution")

        monkeypatch.setattr(sp.subprocess, "run", _fail)
        with pytest.raises(sp.SetupError, match="install piper-tts"):
            sp.install_piper(Path("venv-python"))

    def test_a_missing_interpreter_is_a_setup_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _absent(cmd: list[str], **kwargs: Any) -> None:
            raise FileNotFoundError(cmd[0])

        monkeypatch.setattr(sp.subprocess, "run", _absent)
        with pytest.raises(sp.SetupError, match="not found"):
            sp.install_piper(Path("no-such-python"))


class TestMain:
    def test_check_only_passes_when_every_tool_is_present(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sp.shutil, "which", lambda tool: f"/usr/bin/{tool}")
        assert sp.main(["--check-only"]) == sp.EXIT_OK
        assert "blender  ok" in capsys.readouterr().out

    def test_a_missing_tool_exits_with_the_tools_code(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            sp.shutil, "which", lambda tool: None if tool == "blender" else "/usr/bin/x"
        )
        assert sp.main([]) == sp.EXIT_MISSING_TOOLS
        assert "install blender" in capsys.readouterr().err

    def test_a_bad_voice_name_exits_with_the_setup_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sp.shutil, "which", lambda tool: f"/usr/bin/{tool}")
        assert sp.main(["--voice", "not-a-voice", "--venv", str(tmp_path / "v")]) == sp.EXIT_SETUP
        assert "not of the form" in capsys.readouterr().err

    def test_a_full_setup_runs_each_step_and_reports_the_paths(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        fake_urlopen: list[str],
    ) -> None:
        monkeypatch.setattr(sp.shutil, "which", lambda tool: f"/usr/bin/{tool}")
        venv = tmp_path / "venv"
        venv_python = venv / "bin" / "python"

        def _fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if cmd[1:3] == ["-m", "venv"]:
                venv_python.parent.mkdir(parents=True)
                venv_python.write_text("")
            elif cmd[0] == str(venv_python) and "piper" in cmd:
                Path(cmd[cmd.index("-f") + 1]).write_bytes(b"RIFF")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            elif cmd[0] == "ffprobe":
                return subprocess.CompletedProcess(cmd, 0, "1.2\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(sp.subprocess, "run", _fake_run)
        code = sp.main(["--venv", str(venv), "--voices-dir", str(tmp_path / "voices")])
        out = capsys.readouterr().out

        assert code == sp.EXIT_OK
        assert "piper ready" in out
        assert f"--python {venv_python}" in out
        assert (tmp_path / "voices" / "en_US-lessac-medium.onnx").is_file()
        assert len(fake_urlopen) == 2

    def test_a_synthesis_failure_exits_with_the_synthesis_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_urlopen: list[str]
    ) -> None:
        monkeypatch.setattr(sp.shutil, "which", lambda tool: f"/usr/bin/{tool}")
        venv = tmp_path / "venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("")

        def _fail(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if "piper" in cmd:
                return subprocess.CompletedProcess(cmd, 1, "", "onnx load failed")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(sp.subprocess, "run", _fail)
        code = sp.main(["--venv", str(venv), "--voices-dir", str(tmp_path / "voices")])
        assert code == sp.EXIT_SYNTHESIS
