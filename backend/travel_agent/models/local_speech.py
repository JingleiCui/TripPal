"""Offline speech adapters. Model downloads belong to setup, never to user requests."""
from functools import lru_cache
from pathlib import Path
import io
import platform
import subprocess
import tempfile

from ..providers.base import ProviderError


@lru_cache(maxsize=1)
def recognizer(model):
    from huggingface_hub import snapshot_download
    from faster_whisper import WhisperModel

    path = Path(model)
    source = str(path) if path.is_dir() else snapshot_download(model, local_files_only=True)
    return WhisperModel(source, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)


def transcribe(wav, spec):
    try:
        segments, _ = recognizer(spec.model).transcribe(
            io.BytesIO(wav), language="zh", beam_size=5, vad_filter=False,
        )
        text = "".join(segment.text for segment in segments).strip()
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        raise ProviderError("asr_unavailable", "本地转写模型未就绪，请先运行本地模型准备脚本") from exc
    if not text:
        raise ProviderError("schema", "未识别到清晰语音，请重新录音")
    return {"text": text, "requires_confirmation": True, "model": spec.model}


def synthesize(text, spec):
    if platform.system() != "Darwin":
        raise ProviderError("tts_unavailable", "本地系统朗读当前需要 macOS say；此平台需另配本地 TTS 适配器")
    try:
        with tempfile.TemporaryDirectory(prefix="tripal-speech-") as folder:
            source, output = Path(folder) / "speech.aiff", Path(folder) / "speech.wav"
            subprocess.run(
                ["say", "-v", spec.model, "-o", str(source), "--file-format=AIFF", "-f", "-"],
                input=text, text=True, capture_output=True, check=True, timeout=spec.timeout,
            )
            subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
                 "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-y", str(output)],
                capture_output=True, check=True, timeout=spec.timeout,
            )
            return output.read_bytes()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderError("tts_unavailable", "本地朗读失败，请检查系统中文声音与 FFmpeg") from exc
