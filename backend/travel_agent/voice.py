"""Optional Qwen ASR/TTS adapters. No provider call occurs while voice is disabled."""

import base64
import json
from pathlib import Path
import subprocess
import tempfile
import httpx  # noqa: F401  # 保留模块引用：测试替身经 voice.httpx.Client 注入，网关共用同一模块
from .providers.base import ProviderError
from .models import gateway
from .models.registry import ConfigurationError, ready as slot_ready, resolve

TTS_PATH = "/api/v1/services/aigc/multimodal-generation/generation"


def enabled(slot="asr"):
    if not slot_ready(slot):
        raise ProviderError("disabled", "语音尚未启用，需要先完成模型账号与额度配置")


def ready():
    """配置是否齐备。注意：配置存在不等于已与真实服务联调通过。"""
    return slot_ready("asr")


def voice_key():
    """凭证解析统一交给 registry；跨域名绝不复用对话 Key。"""
    try:
        return resolve("asr").api_key
    except ConfigurationError:
        return ""


def normalize(raw):
    if not raw or len(raw) > 5 * 1024 * 1024:
        raise ValueError("音频为空或超过 5 MB")
    with tempfile.TemporaryDirectory(prefix="travel-voice-") as folder:
        source = Path(folder) / "input.bin"
        output = Path(folder) / "normalized.wav"
        source.write_bytes(raw)
        limits = [
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "wav,mp3,ogg,matroska,webm,mov,aac",
        ]
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    *limits,
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0))
            if duration > 60:
                raise ValueError("单段语音最长 60 秒")
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    *limits,
                    "-i",
                    str(source),
                    "-threads",
                    "1",
                    "-t",
                    "60",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-y",
                    str(output),
                ],
                capture_output=True,
                timeout=20,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError, TypeError) as exc:
            raise ValueError("音频无法解码，请检查格式及本机 FFmpeg") from exc
        return output.read_bytes()


def transcribe(raw):
    enabled()
    wav = normalize(raw)
    try:
        spec = resolve("asr")
    except ConfigurationError as exc:
        raise ProviderError("configuration", str(exc)) from exc
    if spec.protocol == "local":
        return gateway.transcribe_local(wav, spec)
    body = {
        "model": spec.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": "data:audio/wav;base64," + base64.b64encode(wav).decode()},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": False},
    }
    text = gateway.post_chat(
        "asr",
        body,
        label="语音识别",
        failure_code="asr_failed",
        unavailable_code="asr_unavailable",
        spec=spec,
    )
    return {"text": text, "requires_confirmation": True, "model": spec.model}


def synthesize(text):
    enabled("tts")
    if not text.strip() or len(text) > 800:
        raise ValueError("朗读文字应为 1—800 字")
    try:
        spec = resolve("tts")
    except ConfigurationError as exc:
        raise ProviderError("configuration", str(exc)) from exc
    if spec.protocol == "local":
        return gateway.synthesize_local(text, spec)
    payload = gateway.post_json(
        "tts",
        TTS_PATH,
        {
            "model": spec.model,
            "input": {"text": text, "voice": "Cherry", "language_type": "Chinese"},
        },
        label="语音合成",
        failure_code="tts_failed",
        unavailable_code="tts_unavailable",
        spec=spec,
    )
    output = payload.get("output") or {}
    audio_info = output.get("audio") or {} if isinstance(output, dict) else {}
    url = audio_info.get("url", "") if isinstance(audio_info, dict) else ""
    return gateway.download(
        url if isinstance(url, str) else "",
        allowed_suffix=".aliyuncs.com",
        max_bytes=10 * 1024 * 1024,
        unavailable_code="tts_unavailable",
        label="语音合成",
    )
