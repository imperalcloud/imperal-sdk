# tests/test_sdl_facet_media.py
"""SDL Phase 2 — Media & Files family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.media import (
    FileObject, ImageMedia, AudioTrack, VideoTrack, Archive, ContentSafety, Transcribable,
)


class MediaDoc(Entity, FileObject, ImageMedia, AudioTrack, VideoTrack):
    pass


def test_media_facets_compose_and_are_optional():
    d = MediaDoc(id=1, title="x")
    assert d.filename is None
    assert d.width is None
    assert d.audio_codec is None
    assert d.video_codec is None


def test_media_facets_accept_values():
    d = MediaDoc(
        id=1, title="x",
        filename="clip.mp4",
        mime_type="video/mp4",
        width=1920, height=1080,
        audio_codec="aac",
        video_codec="h264",
        fps=29.97,
        video_bitrate_kbps=4000,
    )
    assert d.filename == "clip.mp4"
    assert d.width == 1920
    assert d.audio_codec == "aac"
    assert d.video_codec == "h264"
    assert d.fps == 29.97
    assert d.video_bitrate_kbps == 4000


def test_media_roles_present():
    roles = roles_of(MediaDoc)
    assert roles["filename"] == "media.filename"
    assert roles["mime_type"] == "media.mime_type"
    assert roles["width"] == "media.width"
    assert roles["audio_codec"] == "media.audio_codec"
    assert roles["video_codec"] == "media.video_codec"
    assert roles["video_bitrate_kbps"] == "media.video_bitrate_kbps"


def test_archive_and_safety_and_transcribable_roles():
    class ArchiveDoc(Entity, Archive, ContentSafety, Transcribable):
        pass

    roles = roles_of(ArchiveDoc)
    assert roles["archive_format"] == "media.archive_format"
    assert roles["scan_state"] == "media.scan_state"
    assert roles["transcript"] == "media.transcript"


def test_content_safety_values():
    class SafetyDoc(Entity, ContentSafety):
        pass

    now = datetime(2026, 5, 31, 10, 0, 0)
    d = SafetyDoc(id=1, title="x", scan_state="clean", is_nsfw=False, scanned_at=now)
    assert d.scan_state == "clean"
    assert d.is_nsfw is False
    assert d.scanned_at == now
