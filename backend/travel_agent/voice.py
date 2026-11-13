"""Optional Qwen ASR/TTS adapters. No provider call occurs while voice is disabled."""

import base64
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlparse
import httpx
from .config import settings
from .providers.base import ProviderError


def enabled():
    if not settings.voice_enabled or not voice_key():
        raise ProviderError("disabled", "语音尚未启用，需要先完成模型账号与额度配置")


def voice_key():
    return settings.voice_api_key or (settings.model_api_key if settings.model_provider == "openai" else "")


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
    body = {
        "model": settings.asr_model,
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
    with httpx.Client(timeout=60) as client:
        response = client.post(
            settings.voice_api_base_url + "/compatible-mode/v1/chat/completions",
            headers={"Authorization": "Bearer " + voice_key()},
            json=body,
        )
    if response.status_code != 200:
        raise ProviderError("asr_failed", "语音识别服务拒绝或未完成请求，请核对模型、地域及额度")
    try:
        text = response.json()["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError()
        return {"text": text, "requires_confirmation": True, "model": settings.asr_model}
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ProviderError("schema", "语音识别返回结构不符合约定") from exc


def synthesize(text):
    enabled()
    if not text.strip() or len(text) > 800:
        raise ValueError("朗读文字应为 1—800 字")
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        response = client.post(
            settings.voice_api_base_url + "/api/v1/services/aigc/multimodal-generation/generation",
            headers={"Authorization": "Bearer " + voice_key()},
            json={
                "model": settings.tts_model,
                "input": {"text": text, "voice": "Cherry", "language_type": "Chinese"},
            },
        )
        if response.status_code != 200:
            raise ProviderError("tts_failed", "语音合成未完成，请核对模型、地域与额度")
        url = response.json().get("output", {}).get("audio", {}).get("url", "")
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or not parsed.hostname.endswith(".aliyuncs.com")
        ):
            raise ProviderError("schema", "语音返回地址不在允许的服务域名内")
        url = "https://" + url.split("://", 1)[1]
        audio = bytearray()
        with client.stream("GET", url) as stream:
            stream.raise_for_status()
            for piece in stream.iter_bytes():
                audio.extend(piece)
                if len(audio) > 10 * 1024 * 1024:
                    raise ProviderError("size", "合成音频超过返回上限")
        return bytes(audio)
