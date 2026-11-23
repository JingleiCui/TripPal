"""Failure-path contracts; simulated models here are not model-quality evaluations."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from travel_agent.config import settings
from travel_agent.conversation import extract, to_requirements


def test_change_city_invalidates_previous_city_allocation():
    slots, _, _, _ = extract("北京两天、上海两天", {}, fixture=True)
    slots, _, _, _ = extract("改去杭州三天", slots, fixture=True)
    assert to_requirements(slots).city == "杭州"
    assert not to_requirements(slots).city_stays


def test_local_jwt_key_creation_is_atomic(tmp_path, monkeypatch):
    from travel_agent.security import signing_key

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_secret", "")
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: signing_key(), range(32)))
    assert len(set(values)) == 1 and len(values[0]) >= 32


def test_model_region_error_is_actionable_without_raw_exception():
    from travel_agent.model_errors import classify

    error = RuntimeError("FAILED_PRECONDITION: User location is not supported for the API use. key=private")
    safe = classify(error)
    assert safe.code == "model_region" and "密钥已读取" in str(safe)
    assert "private" not in str(safe)


def test_password_min_length_is_six():
    from travel_agent.lifecycle_api import ResetInput
    from travel_agent.schemas import Credentials

    assert Credentials(name="tester", password="123456").password == "123456"
    assert ResetInput(token="t" * 20, password="123456").password == "123456"

    with pytest.raises(ValidationError):
        Credentials(name="tester", password="12345")
    with pytest.raises(ValidationError):
        ResetInput(token="t" * 20, password="12345")
