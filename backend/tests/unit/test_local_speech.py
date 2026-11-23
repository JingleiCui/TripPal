from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from travel_agent import voice
from travel_agent.config import Settings, settings
from travel_agent.models import local_speech
from travel_agent.models.registry import resolve
from travel_agent.providers.base import ProviderError


def test_local_speech_slots_require_no_key():
    config = Settings(
        model_slots={
            s: {"provider": "local_speech", "model": "test", "enabled": True} for s in ("asr", "tts")
        }
    )
    assert resolve("asr", config).ready
    assert resolve("tts", config).protocol == "local"
    assert not resolve("tts", config).requires_key


def test_voice_routes_to_local_without_http(monkeypatch):
    monkeypatch.setattr(
        settings,
        "model_slots",
        {s: {"provider": "local_speech", "model": "test", "enabled": True} for s in ("asr", "tts")},
    )
    monkeypatch.setattr(voice, "normalize", lambda raw: b"normalized")
    asr, tts, network = Mock(return_value={"text": "北京"}), Mock(return_value=b"RIFF"), Mock()
    monkeypatch.setattr(voice.gateway, "transcribe_local", asr)
    monkeypatch.setattr(voice.gateway, "synthesize_local", tts)
    monkeypatch.setattr(voice.gateway, "post_chat", network)
    assert voice.transcribe(b"input")["text"] == "北京"
    assert voice.synthesize("北京") == b"RIFF"
    assert asr.call_args.args[0] == b"normalized"
    network.assert_not_called()


def test_transcribe_consumes_lazy_segments_and_requires_confirmation(monkeypatch):
    fake = Mock()
    fake.transcribe.return_value = (iter([SimpleNamespace(text="北京"), SimpleNamespace(text="两天")]), None)
    monkeypatch.setattr(local_speech, "recognizer", lambda model: fake)
    result = local_speech.transcribe(b"wav", SimpleNamespace(model="test"))
    assert result == {"text": "北京两天", "requires_confirmation": True, "model": "test"}


def test_empty_transcription_is_not_success(monkeypatch):
    fake = Mock()
    fake.transcribe.return_value = (iter([]), None)
    monkeypatch.setattr(local_speech, "recognizer", lambda model: fake)
    with pytest.raises(ProviderError, match="未识别"):
        local_speech.transcribe(b"wav", SimpleNamespace(model="test"))


def test_system_tts_reports_platform_requirement(monkeypatch):
    monkeypatch.setattr(local_speech.platform, "system", lambda: "Linux")
    with pytest.raises(ProviderError, match="macOS"):
        local_speech.synthesize("北京", SimpleNamespace(model="Tingting"))
