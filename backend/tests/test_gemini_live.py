import asyncio

from backend.app.live.gemini_live import GeminiLiveConnection


class _DummyContextManager:
    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _DummyBlob:
    def __init__(self, *, data: bytes, mime_type: str) -> None:
        self.data = data
        self.mime_type = mime_type


class _DummyTypes:
    Blob = _DummyBlob


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_realtime_input(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_send_audio_chunk_uses_audio_only_input() -> None:
    fake_session = _FakeSession()
    connection = GeminiLiveConnection(
        _context_manager=_DummyContextManager(),
        _session=fake_session,
        _supports_explicit_activity_end=True,
        _types=_DummyTypes,
    )

    asyncio.run(
        connection.send_audio_chunk(
            audio_bytes=b"\x00\x01",
            mime_type="audio/pcm;rate=16000",
            is_final_chunk=True,
        )
    )

    assert len(fake_session.calls) == 1
    assert set(fake_session.calls[0]) == {"audio"}
    blob = fake_session.calls[0]["audio"]
    assert isinstance(blob, _DummyBlob)
    assert blob.data == b"\x00\x01"
    assert blob.mime_type == "audio/pcm;rate=16000"
