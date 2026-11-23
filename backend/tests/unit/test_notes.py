import io
import json
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
from travel_agent.notes import extract, jobs, source


def png(width=64, height=64):
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, "PNG")
    return out.getvalue()


def page(note):
    return (
        "<script>window.__INITIAL_STATE__="
        + json.dumps({"note": {"noteDetailMap": {"id": {"note": note}}}})
        + ";</script>"
    )


def test_share_link_is_not_treated_as_note_body():
    assert source.extract_url("推荐攻略 https://xhslink.com/a/abc 。") == "https://xhslink.com/a/abc"
    assert not source.extract_url("https://xiaohongshu.com.attacker.test/explore/id")
    result = source.parse_page(
        '<title>登录</title><meta property="og:description" content="请扫码登录">',
        "https://www.xiaohongshu.com/explore/id",
    )
    assert not result["complete"] and not result["body"]


def test_note_body_and_image_order_are_read_without_eval():
    raw = page(
        {
            "noteId": "id",
            "title": "攻略",
            "desc": "完整正文" * 500,
            "imageList": [
                {"urlDefault": "https://sns-webpic.xhscdn.com/one"},
                {"urlDefault": "https://sns-webpic.xhscdn.com/two"},
            ],
        }
    )
    result = source.parse_page(raw, "https://www.xiaohongshu.com/explore/id")
    assert result["complete"] and len(result["body"]) > 800
    assert result["images"] == ["https://sns-webpic.xhscdn.com/one", "https://sns-webpic.xhscdn.com/two"]
    result = source.parse_page(
        page({"desc": "", "imageList": [{"url": "https://sns-webpic.xhscdn.com/one"}]}),
        "https://www.xiaohongshu.com/explore/id",
    )
    assert result["complete"] and result["images"]
    assert source.json_state('{"a":undefined,"b":"undefined"};') == {"a": None, "b": "undefined"}


def test_metadata_is_explicitly_partial_and_wrong_note_is_not_read():
    raw = (
        page({"noteId": "other", "title": "别篇笔记", "desc": "不能采用"})
        + '<meta property="og:description" content="只是一段预览">'
    )
    result = source.parse_page(raw, "https://www.xiaohongshu.com/explore/id")
    assert not result["complete"] and result["body_source"] == "metadata_preview"
    assert result["body"] == "只是一段预览"


@pytest.mark.parametrize(
    "url",
    [
        "http://www.xiaohongshu.com/a",
        "https://localhost/a",
        "https://127.0.0.1/a",
        "https://www.xiaohongshu.com:8443/a",
        "https://u:p@www.xiaohongshu.com/a",
    ],
)
def test_source_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        source.validate_url(url)


def cookie_file(value, mode=0o600):
    path = Path("/tmp") / ("tripal-note-cookie-" + uuid.uuid4().hex + ".txt")
    path.write_text(value)
    path.chmod(mode)
    return path


def test_login_cookie_is_scoped_to_configured_note_hosts(monkeypatch):
    from travel_agent.config import settings

    cookie = cookie_file("# 浏览器 Network 里复制的 Cookie 请求头\nweb_session=abc; a1=xyz\n")
    monkeypatch.setattr(settings, "note_login_enabled", True)
    monkeypatch.setattr(settings, "note_cookie_file", str(cookie))
    monkeypatch.setattr(settings, "note_cookie_hosts", ["www.xiaohongshu.com"])

    assert source._login_cookie("www.xiaohongshu.com") == "web_session=abc; a1=xyz"
    assert source._login_cookie("xiaohongshu.com") == ""
    assert source._login_cookie("sns-webpic.xhscdn.com") == ""


def test_world_readable_cookie_file_is_rejected(monkeypatch):
    from travel_agent.config import settings

    cookie = cookie_file("web_session=abc", mode=0o644)
    monkeypatch.setattr(settings, "note_login_enabled", True)
    monkeypatch.setattr(settings, "note_cookie_file", str(cookie))
    monkeypatch.setattr(settings, "note_cookie_hosts", ["www.xiaohongshu.com"])

    with pytest.raises(ValueError, match="权限过宽"):
        source._login_cookie("www.xiaohongshu.com")


def test_fetch_adds_cookie_to_note_host_but_never_to_image_cdn(monkeypatch):
    from travel_agent.config import settings

    cookie = cookie_file("web_session=abc")
    monkeypatch.setattr(settings, "note_login_enabled", True)
    monkeypatch.setattr(settings, "note_cookie_file", str(cookie))
    monkeypatch.setattr(settings, "note_cookie_hosts", ["www.xiaohongshu.com"])
    monkeypatch.setattr(source, "public_addresses", lambda host: ["8.8.8.8"])
    connection = Mock()
    response = Mock(status=200)
    response.getheader.return_value = "identity"
    response.read.return_value = b"<html></html>"
    connection.return_value.getresponse.return_value = response
    monkeypatch.setattr(source, "PinnedHTTPS", connection)

    source.fetch("https://www.xiaohongshu.com/explore/id")
    headers = connection.return_value.request.call_args.kwargs["headers"]
    assert headers["Cookie"] == "web_session=abc"
    assert headers["Referer"] == "https://www.xiaohongshu.com/"

    connection.reset_mock()
    source.fetch("https://sns-webpic.xhscdn.com/a.jpg", image=True)
    headers = connection.return_value.request.call_args.kwargs["headers"]
    assert "Cookie" not in headers


def test_browser_fallback_recovers_dismissible_login_overlay(monkeypatch):
    monkeypatch.setattr(
        source,
        "fetch",
        lambda url: (url, '<meta property="og:title" content="登录">'.encode()),
    )
    complete = {
        "title": "真实笔记",
        "body": "正文内容",
        "images": ["https://sns-webpic.xhscdn.com/a"],
        "body_source": "note_body",
        "complete": True,
        "url": "https://www.xiaohongshu.com/explore/id",
    }
    monkeypatch.setattr(source, "_browser_read", lambda url: complete)

    result = source.read_note("https://www.xiaohongshu.com/explore/id")
    assert result == complete


def test_browser_fallback_recovers_http_fetch_error(monkeypatch):
    def boom(url):
        raise ValueError("笔记来源未能读取（HTTP 403）")

    monkeypatch.setattr(source, "fetch", boom)
    complete = {
        "title": "真实笔记",
        "body": "正文内容",
        "images": [],
        "body_source": "dom_after_login_dismiss",
        "complete": True,
        "url": "https://www.xiaohongshu.com/explore/id",
    }
    monkeypatch.setattr(source, "_browser_read", lambda url: complete)

    assert source.read_note("https://www.xiaohongshu.com/explore/id") == complete


def test_private_dns_and_unsafe_redirect_never_connect(monkeypatch):
    monkeypatch.setattr(
        source.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("10.0.0.1", 443))]
    )
    connection = Mock()
    monkeypatch.setattr(source, "PinnedHTTPS", connection)
    with pytest.raises(ValueError):
        source.fetch("https://www.xiaohongshu.com/explore/id")
    connection.assert_not_called()
    monkeypatch.setattr(source, "public_addresses", lambda host: ["8.8.8.8"])
    response = Mock(status=302)
    response.getheader.return_value = "https://127.0.0.1/private"
    connection.return_value.getresponse.return_value = response
    with pytest.raises(ValueError):
        source.fetch("https://www.xiaohongshu.com/explore/id")
    assert connection.call_count == 1
    assert connection.call_args.args == ("www.xiaohongshu.com", "8.8.8.8")


def test_long_image_is_tiled_without_scaling_or_losing_the_bottom():
    parts = extract.tiles(png(1000, 4000))
    assert len(parts) == 3
    assert parts[0][0] == [0, 0, 1000, 1536]
    assert parts[-1][0][-1] == 4000
    assert extract.merge_tiles(["第一行\n第二行", "第二行\n第三行"]) == "第一行\n第二行\n第三行"


def test_photo_and_camera_watermark_are_skipped_but_uncertain_images_are_read(monkeypatch):
    for response, expected in [
        ("PHOTO", "photo"),
        ("WATERMARK", "watermark"),
        ("TEXT", "text"),
        ("不确定", "text"),
    ]:
        monkeypatch.setattr(extract, "_read_image", lambda *a, response=response, **k: {"text": response})
        assert extract.classify_image(png()) == expected
    assert extract.classify_image(png(100, 1000)) == "text"


def test_facts_require_verbatim_evidence_and_keep_contradictions(monkeypatch):
    from travel_agent.agent import structured

    output = extract.Facts(
        facts=[
            extract.Fact(kind="place", text="颐和园", evidence="北京颐和园", city="北京"),
            extract.Fact(kind="place", text="故宫", evidence="虚构引文"),
            extract.Fact(kind="place", text="推测地点", evidence="北京颐和园"),
            extract.Fact(kind="cost", text="门票 30 元", evidence="门票 30 元"),
            extract.Fact(kind="cost", text="门票 60 元", evidence="门票 60 元"),
        ]
    )
    monkeypatch.setattr(structured, "generate", lambda *a, **k: output)
    facts = extract.extract_facts("北京颐和园。门票 30 元。另一个作者写门票 60 元。")
    assert [f["kind"] for f in facts] == ["place", "cost", "cost"]


def test_retry_invalidates_only_affected_evidence():
    data = {
        "facts": [
            {"id": "one", "sources": [{"anchor": "image:pic:1"}]},
            {"id": "two", "sources": [{"anchor": "manual_body:1"}, {"anchor": "image:pic:1"}]},
        ],
        "fact_blocks": {"image:pic:1": "hash", "manual_body:1": "other"},
    }
    jobs.invalidate_source(data, "image:pic:")
    assert [f["id"] for f in data["facts"]] == ["two"]
    assert data["facts"][0]["sources"] == [{"anchor": "manual_body:1"}]
    assert data["fact_blocks"] == {"manual_body:1": "other"}


def test_camera_footer_fallback_never_discards_actual_travel_text():
    assert extract.camera_watermark_only("SONY A7 IV | 35mm f/2.8 1/250s ISO100")
    assert not extract.camera_watermark_only("北京颐和园路线，SONY A7 IV 35mm ISO100")
    assert not extract.camera_watermark_only("Beijing travel guide\nSONY A7 IV 35mm ISO100")
    assert not extract.camera_watermark_only("门票 100 元，相机博物馆")
