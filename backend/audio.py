import base64
import struct
from typing import Optional


def pcm_to_base64(pcm_data: bytes) -> str:
    """Convert raw PCM bytes to base64 string."""
    return base64.b64encode(pcm_data).decode("utf-8")


def base64_to_pcm(b64_string: str) -> bytes:
    """Convert base64 string to raw PCM bytes."""
    return base64.b64decode(b64_string)


def create_wav_header(
    num_channels: int = 1,
    sample_rate: int = 16000,
    bits_per_sample: int = 16,
    num_samples: Optional[int] = None,
) -> bytes:
    """Create a minimal WAV header for PCM audio."""
    data_size = (num_samples or 0) * num_channels * (bits_per_sample // 8)
    chunk_size = 36 + data_size
    byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
    block_align = num_channels * (bits_per_sample // 8)

    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )


def pcm_to_wav_base64(
    pcm_data: bytes,
    sample_rate: int = 24000,
    num_channels: int = 1,
    bits_per_sample: int = 16,
) -> str:
    """Wrap raw PCM in a WAV container and return as base64."""
    num_samples = len(pcm_data) // (num_channels * bits_per_sample // 8)
    header = create_wav_header(num_channels, sample_rate, bits_per_sample, num_samples)
    return base64.b64encode(header + pcm_data).decode("utf-8")
