import uuid
from unittest.mock import patch

import pytest
from travel_agent.config import settings
from travel_agent.providers import amap
from travel_agent.providers.base import ProviderError, read_json, safe_url


def test_readonly_retry_is_bounded():
    import httpx

    with (
        patch("travel_agent.providers.base.httpx.Client") as client,
        patch("travel_agent.providers.base.time.sleep"),
    ):
        client.return_value.__enter__.return_value.get.side_effect = httpx.ReadTimeout("timeout")
        with pytest.raises(ProviderError, match="超时"):
            read_json("https://test.invalid/retry", {"q": uuid.uuid4().hex})
        assert client.return_value.__enter__.return_value.get.call_count == 3


def test_business_error_not_cached():
    response = type(
        "R", (), {"status_code": 200, "json": lambda _: {"status": "0", "info": "INVALID_USER_KEY"}}
    )()
    with patch("travel_agent.providers.base.httpx.Client") as client:
        client.return_value.__enter__.return_value.get.return_value = response
        with pytest.raises(ProviderError, match="INVALID_USER_KEY"):
            read_json("https://test.invalid/schema", {"q": uuid.uuid4().hex})
        assert client.return_value.__enter__.return_value.get.call_count == 1


def test_no_unsafe_source_links():
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("https://user:secret@example.com") is None


def test_provider_nonfinite_numbers_are_unknown():
    assert amap.number("NaN") is None
    assert amap.number("Infinity") is None
    assert amap.number("-4") is None


def test_voice_disabled_does_not_call_cloud():
    from travel_agent.voice import transcribe

    with patch.object(settings, "voice_enabled", False), patch("travel_agent.voice.httpx.Client") as client:
        with pytest.raises(ProviderError):
            transcribe(b"fake")
        assert not client.called
