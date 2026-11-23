"""Bounded public XHS fetcher: pinned public IPs, verified TLS, validated redirects."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
import os
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

NOTE_HOSTS = {
    "xiaohongshu.com",
    "www.xiaohongshu.com",
    "xhslink.com",
    "www.xhslink.com",
    "rednote.com",
    "www.rednote.com",
}
IMAGE_DOMAINS = ("xhscdn.com", "xiaohongshu.com")
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def extract_url(text):
    for match in re.findall(r'https?://[^\s<>"\[\]()\u3000]+', text or ""):
        value = match.rstrip("。，；！、）)]}")
        p = urlparse(value)
        if p.hostname in NOTE_HOSTS:
            return value.replace("http://", "https://", 1)
    return ""


def validate_url(url, image=False):
    p = urlparse(url)
    host = (p.hostname or "").lower()
    allowed = any(host == d or host.endswith("." + d) for d in IMAGE_DOMAINS) if image else host in NOTE_HOSTS
    if p.scheme != "https" or not allowed or p.username or p.password or p.port not in {None, 443}:
        raise ValueError("链接不属于支持的笔记或图片来源")
    return host


def _login_cookie(host: str) -> str:
    """Return the user's own session cookie only for explicitly allowed note hosts.

    The file is local, mode 0600 and never sent to image CDNs or stored in the database.
    """
    from ..config import settings

    if not settings.note_login_enabled or host not in settings.note_cookie_hosts:
        return ""
    if not settings.note_cookie_file:
        raise ValueError("已启用本人会话，但未配置 note_cookie_file")
    path = Path(settings.note_cookie_file).expanduser()
    if not path.is_file():
        raise ValueError("本人会话 Cookie 文件不存在，请检查 note_cookie_file")
    if path.stat().st_mode & 0o077:
        raise ValueError("Cookie 文件权限过宽，请执行 chmod 600 后再试")
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise ValueError("Cookie 文件为空，请写入浏览器复制的 Cookie 请求头")
    value = lines[0]
    if len(value) > 16384:
        raise ValueError("Cookie 内容过长，请重新从浏览器复制")
    return value


def _browser_read(url: str):
    """Dismiss closable login overlays in a real browser and read note state/DOM."""
    from ..config import settings

    if not settings.note_browser_fallback:
        return None
    validate_url(url)
    script = Path(settings.note_browser_reader)
    if not script.is_file():
        return None
    env = os.environ.copy()
    if not settings.note_browser_headless:
        env["TRIPAL_XHS_HEADED"] = "1"
    if settings.note_browser_user_data_dir:
        env["TRIPAL_XHS_USER_DATA_DIR"] = settings.note_browser_user_data_dir
    try:
        result = subprocess.run(
            ["node", str(script), url],
            capture_output=True,
            text=True,
            timeout=settings.note_browser_timeout,
            cwd=str(script.parent),
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode:
        return None
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    body = str(data.get("body") or "")[:200000]
    images = []
    for value in data.get("images") or []:
        if not isinstance(value, str):
            continue
        try:
            validate_url(value, True)
        except ValueError:
            continue
        images.append(value)
    if not data.get("complete") or (not body and not images):
        return None
    return {
        "title": str(data.get("title") or "小红书攻略")[:200],
        "body": body,
        "images": list(dict.fromkeys(images)),
        "body_source": str(data.get("body_source") or "browser"),
        "complete": True,
        "url": str(data.get("url") or url),
    }


def public_addresses(host):
    addresses = list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    # Some local VPNs synthesize 198.18/15 addresses. Resolve the allowlisted hostname
    # through a fixed TLS-verified public DNS service, then connect ONLY to verified public IPs.
    # RFC1918/loopback answers are always rejected; no general private-network exception exists.
    fake_range = ipaddress.ip_network("198.18.0.0/15")
    if addresses and all(ipaddress.ip_address(a) in fake_range for a in addresses):
        from ..config import settings

        if settings.note_public_dns_fallback:
            with httpx.Client(timeout=10) as client:
                result = client.get("https://dns.google/resolve", params={"name": host, "type": "A"})
                result.raise_for_status()
                addresses = [a["data"] for a in result.json().get("Answer", []) if a.get("type") == 1]
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("来源地址无法安全访问，请补充正文和图片")
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=20, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch(url, *, image=False):
    limit = MAX_IMAGE_BYTES if image else MAX_HTML_BYTES
    for _ in range(6):
        host = validate_url(url, image)
        addresses = public_addresses(host)
        p = urlparse(url)
        conn = PinnedHTTPS(host, addresses[0])
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "identity",
        }
        # 图片 CDN 永远不带 Cookie；会话只发给用户显式允许的笔记域名。
        if not image:
            cookie = _login_cookie(host)
            if cookie:
                headers["Cookie"] = cookie
                headers["Referer"] = "https://www.xiaohongshu.com/"
        try:
            conn.request(
                "GET",
                p.path + ("?" + p.query if p.query else ""),
                headers=headers,
            )
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if response.status != 200:
                raise ValueError(f"笔记来源未能读取（HTTP {response.status}），可补充正文和图片")
            if response.getheader("Content-Encoding", "identity") not in {"identity", ""}:
                raise ValueError("来源响应编码不支持，请补充正文和图片")
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("来源内容超过大小限制")
            return url, raw
        finally:
            conn.close()
    raise ValueError("笔记链接重定向过多，请补充正文和图片")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.meta = [], {}
        self.script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.script = ""
        if tag == "meta":
            self.meta[attrs.get("property") or attrs.get("name")] = attrs.get("content", "")

    def handle_data(self, data):
        if self.script is not None:
            self.script += data

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append(self.script)
            self.script = None


def json_state(text):
    """Replace JS undefined outside strings only; never eval executable page code."""
    out, quoted, escaped, i = [], False, False, 0
    while i < len(text):
        c = text[i]
        if quoted:
            out.append(c)
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
            i += 1
        elif c == '"':
            quoted = True
            out.append(c)
            i += 1
        elif text.startswith("undefined", i):
            out.append("null")
            i += 9
        else:
            out.append(c)
            i += 1
    return json.JSONDecoder().raw_decode("".join(out))[0]


def parse_page(html, url):
    page = Page()
    page.feed(html)
    note_id = urlparse(url).path.rstrip("/").split("/")[-1]
    for script in page.scripts:
        marker = re.search(r"(?:window\.)?__INITIAL_STATE__\s*=\s*", script)
        if not marker:
            continue
        try:
            state = json_state(script[marker.end() :])
            notes = state.get("note", {}).get("noteDetailMap", {})
            entry = notes.get(note_id)
            if entry is None and len(notes) == 1:
                entry = next(iter(notes.values()))
            note = (entry or {}).get("note", {})
            if note.get("noteId") and note["noteId"] != note_id:
                continue
            text = note.get("desc", "")
            if not isinstance(text, str) or (not text.strip() and not note.get("imageList")):
                continue
            images = []
            for item in note.get("imageList", []):
                options = [item.get("urlDefault"), item.get("urlPre"), item.get("url")]
                options += [v.get("url") for v in item.get("infoList", []) if isinstance(v, dict)]
                for candidate in options:
                    if isinstance(candidate, str) and candidate:
                        candidate = candidate.replace("http://", "https://", 1)
                        try:
                            validate_url(candidate, True)
                        except ValueError:
                            continue
                        images.append(candidate)
                        break
            return {
                "title": str(note.get("title") or "小红书攻略")[:200],
                "body": text,
                "images": list(dict.fromkeys(images)),
                "body_source": "note_body",
                "complete": True,
            }
        except (ValueError, TypeError, AttributeError, KeyError):
            continue
    # Metadata is explicitly partial: it can be a shortened preview, never the full note.
    desc = page.meta.get("og:description", "")
    login_page = re.search(
        r"log\s*in|sign\s*in|登录|安全验证|访问受限|verification", page.meta.get("og:title", ""), re.I
    )
    if login_page:
        desc = ""
        page.meta["og:title"] = "小红书攻略"
    if not desc or any(
        w in desc for w in ["登录后", "扫码登录", "安全验证", "访问受限", "Log in", "Sign in"]
    ):
        desc = ""
    return {
        "title": page.meta.get("og:title", "小红书攻略")[:200],
        "body": desc,
        "images": [],
        "body_source": "metadata_preview",
        "complete": False,
    }


def read_note(url):
    try:
        final, raw = fetch(url)
        result = parse_page(raw.decode("utf-8", errors="replace"), final)
        result["url"] = final
    except Exception as exc:
        browser = _browser_read(url)
        if browser:
            return browser
        raise exc
    if not result.get("complete"):
        browser = _browser_read(url)
        if browser:
            return browser
    return result
