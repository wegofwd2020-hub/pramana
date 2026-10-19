"""Render a compliance lesson spec to MP4 with Blender, ffmpeg and Piper.

See ``cli.py`` for the entry point and ``openspec/changes/add-blender-lesson-renderer``
for the design. The renderer is deterministic: the same approved spec produces the
same frames, and the provenance record pins the exact artifact.
"""
