import io
import uuid
from unittest.mock import Mock

import pytest
from PIL import Image
from travel_agent.db import Attachment, Session
from travel_agent.notes import extract, jobs, source


def png(color="white"):
    out = io.BytesIO()
    Image.new("RGB", (80, 80), color).save(out, "PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def offline_jobs(monkeypatch):
    monkeypatch.setattr(jobs, "dispatch", lambda ident: None)
    monkeypatch.setattr(jobs, "match_places", lambda *a: None)
    monkeypatch.setattr(
        extract,
        "extract_facts",
        lambda text: (
            [
                {"kind": "city", "text": "北京", "city": "北京", "evidence": "北京"},
                {"kind": "place", "text": "颐和园", "city": "北京", "evidence": "颐和园"},
            ]
            if "颐和园" in text
            else []
        ),
    )


def create(account, **kwargs):
    result = account.post("/api/v1/note-imports", data={"body_text": "北京颐和园，一日游。"}, **kwargs)
    assert result.status_code == 202, result.text
    return result.json()["id"]


def test_manual_import_review_reference_and_duplicate_import(account):
    ident = create(account)
    assert create(account) == ident
    jobs.process(ident)
    note = account.get(f"/api/v1/note-imports/{ident}").json()
    assert note["parsed"]["status"] == "ready"
    assert "lease" not in note["parsed"]
    facts = note["parsed"]["facts"]
    conv = account.post("/api/v1/conversations", json={"fixture": True}).json()
    payload = {
        "content": "请参考攻略",
        "version": 0,
        "request_key": uuid.uuid4().hex,
        "attachment_ids": [ident],
    }
    assert account.post(f"/api/v1/conversations/{conv['id']}/turns", json=payload).status_code == 422
    result = account.post(
        f"/api/v1/note-imports/{ident}/confirm", json={"selected_fact_ids": [f["id"] for f in facts]}
    )
    assert result.status_code == 200
    reply = account.post(f"/api/v1/conversations/{conv['id']}/turns", json=payload)
    assert reply.status_code == 200, reply.text
    assert reply.json()["slots"]["destination"] == "北京"
    assert not reply.json()["slots"].get("travel_dates")
    assert reply.json()["messages"][-2]["meta"]["attachment_ids"] == [ident]
    # Adoption records sources but never creates a formal itinerary just from the import.
    assert reply.json()["trip_id"] is None
    summary = account.get("/api/v1/note-imports").json()[0]
    assert "parsed" not in summary and summary["status"] == "ready"


def test_auto_confirm_accepts_full_body_without_manual_selection(account, monkeypatch):
    monkeypatch.setattr(extract, "extract_facts", lambda text: [])
    ident = create(account)
    jobs.process(ident)
    result = account.post(
        f"/api/v1/note-imports/{ident}/confirm",
        json={"selected_fact_ids": [], "auto": True},
    )
    assert result.status_code == 200, result.text
    parsed = result.json()["parsed"]
    assert parsed["auto_adopted_at"]
    assert parsed["manual_body"] == "北京颐和园，一日游。"

    conv = account.post("/api/v1/conversations", json={"fixture": True}).json()
    reply = account.post(
        f"/api/v1/conversations/{conv['id']}/turns",
        json={
            "content": "请根据攻略继续回答",
            "version": 0,
            "request_key": uuid.uuid4().hex,
            "attachment_ids": [ident],
        },
    )
    assert reply.status_code == 200, reply.text


def test_bad_link_can_be_supplemented_and_raw_text_is_not_truncated(account, monkeypatch):
    monkeypatch.setattr(source, "read_note", Mock(side_effect=ValueError("笔记暂不可读")))
    r = account.post("/api/v1/note-imports", data={"share_text": "攻略 https://xhslink.com/a/example"})
    ident = r.json()["id"]
    jobs.process(ident)
    note = account.get(f"/api/v1/note-imports/{ident}").json()["parsed"]
    assert note["status"] == "needs_input" and not note["link_body"]
    text = "北京颐和园攻略。" * 200
    r = account.post(f"/api/v1/note-imports/{ident}/sources", data={"body_text": text})
    assert r.status_code == 202
    jobs.process(ident)
    note = account.get(f"/api/v1/note-imports/{ident}").json()["parsed"]
    assert note["manual_body"] == text and len(text) > 800
    assert note["status"] == "ready"
    assert note["url"] == "https://xhslink.com/a/example"


def test_images_skip_watermarks_retry_failed_only_and_owner_image_access(account, monkeypatch):
    classifier = Mock(side_effect=["watermark", "text", "text"])
    monkeypatch.setattr(extract, "classify_image", classifier)
    ocr = Mock(
        side_effect=[RuntimeError("temporary"), {"text": "北京颐和园", "truncated": False, "unclear": False}]
    )
    monkeypatch.setattr(extract, "transcribe_tile", ocr)
    r = account.post(
        "/api/v1/note-imports",
        files=[("files", ("a.png", png(), "image/png")), ("files", ("b.png", png("blue"), "image/png"))],
    )
    assert r.status_code == 202, r.text
    ident = r.json()["id"]
    jobs.process(ident)
    note = account.get(f"/api/v1/note-imports/{ident}").json()["parsed"]
    first, second = note["images"]
    assert first["status"] == "skipped" and second["status"] == "error"
    assert first["skip_reason"] == "仅相机水印，无攻略文字"
    assert account.get(f"/api/v1/note-imports/{ident}/images/{first['id']}").content == png()
    assert all("file" not in image for image in note["images"])
    assert (
        account.post(f"/api/v1/note-imports/{ident}/retry", json={"image_id": second["id"]}).status_code
        == 202
    )
    jobs.process(ident)
    note = account.get(f"/api/v1/note-imports/{ident}").json()["parsed"]
    assert note["status"] == "ready" and note["images"][0]["status"] == "skipped"
    assert classifier.call_count == 2  # Successful classification and ignored photo are reused.
    assert ocr.call_count == 2
    assert account.delete(f"/api/v1/note-imports/{ident}").status_code == 204
    assert account.get(f"/api/v1/note-imports/{ident}").status_code == 404


def test_note_owner_scope_and_forged_facts_are_rejected(account, client):
    ident = create(account)
    jobs.process(ident)
    r = account.post(f"/api/v1/note-imports/{ident}/confirm", json={"selected_fact_ids": ["forged"]})
    assert r.status_code == 422
    from fastapi.testclient import TestClient
    from travel_agent.api import app

    other = TestClient(app)
    auth = other.post(
        "/api/v1/auth/register",
        json={"name": "other-" + uuid.uuid4().hex[:12], "password": "strong-password-test"},
    ).json()
    other.headers["X-CSRF-Token"] = auth["csrf"]
    assert other.get(f"/api/v1/note-imports/{ident}").status_code == 404
    assert other.post(f"/api/v1/note-imports/{ident}/retry", json={}).status_code == 404
    assert other.delete(f"/api/v1/note-imports/{ident}").status_code == 404


def test_lease_fencing_and_resume_do_not_repeat_completed_sources(account, monkeypatch):
    ident = create(account)
    extractor = Mock(return_value=[])
    monkeypatch.setattr(extract, "extract_facts", extractor)
    with Session.begin() as db:
        row = db.get(Attachment, ident)
        data = dict(row.parsed)
        data.update(status="running", lease="another-worker", lease_until="2999-01-01T00:00:00")
        row.parsed = data
    jobs.process(ident)
    extractor.assert_not_called()
    with Session.begin() as db:
        row = db.get(Attachment, ident)
        row.parsed = {**row.parsed, "lease_until": "2000-01-01T00:00:00"}
    jobs.process(ident)
    assert extractor.call_count == 1
    account.post(f"/api/v1/note-imports/{ident}/retry", json={})
    jobs.process(ident)
    assert extractor.call_count == 1


def test_long_transcription_and_truncation_correction_are_retained(account, monkeypatch):
    monkeypatch.setattr(extract, "classify_image", lambda raw: "text")
    full = "北京颐和园攻略文字\n" * 160
    ocr = Mock(
        side_effect=[
            {"text": "截断", "truncated": True, "unclear": False},
            {"text": full, "truncated": False, "unclear": False},
            {"text": "末尾文字", "truncated": False, "unclear": False},
        ]
    )
    monkeypatch.setattr(extract, "transcribe_tile", ocr)
    ident = create(account, files={"files": ("guide.png", png(), "image/png")})
    jobs.process(ident)
    data = account.get(f"/api/v1/note-imports/{ident}").json()["parsed"]
    assert len(data["images"][0]["text"]) > 800
    assert data["images"][0]["text"].endswith("末尾文字")
    assert "截断" not in data["images"][0]["text"]
    assert ocr.call_count == 3


def test_note_images_are_in_private_export_and_account_cleanup(account):
    ident = create(account, files={"files": ("guide.png", png(), "image/png")})
    with Session() as db:
        owner = db.get(Attachment, ident).owner
    export = account.get("/api/v1/privacy/export")
    assert export.status_code == 200
    import zipfile

    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        assert any(name.startswith(f"notes/{ident}/") for name in archive.namelist())
    from travel_agent.db import PrivacyCleanup
    from travel_agent.privacy_cleanup import process_pending

    folder = jobs.directory(owner, ident)
    assert folder.exists()
    # Exercise the durable file cleanup independently of account deletion's other responsibilities.
    with Session.begin() as db:
        db.add(PrivacyCleanup(owner=owner, document_ids=[]))
    process_pending()
    assert not folder.exists()
