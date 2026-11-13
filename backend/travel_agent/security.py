import base64
import hashlib
import hmac
import secrets
from datetime import timedelta, datetime, timezone
from pathlib import Path
import os
import tempfile
import jwt
from fastapi import HTTPException, Request
from .db import Session, LoginSession, User, AccountProfile, now
from .config import settings


def signing_key():
    if settings.jwt_secret:
        if len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT 签名密钥至少 32 字符")
        return settings.jwt_secret
    path = Path(settings.data_dir) / "jwt.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".jwt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(secrets.token_urlsafe(48))
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)
    key = path.read_text().strip()
    if len(key) < 32:
        raise RuntimeError("本机 JWT 密钥不完整，请恢复有效密钥后重启")
    return key


def hash_token(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + key).decode()


def password_valid(password, stored):
    try:
        raw = base64.b64decode(stored)
        return hmac.compare_digest(
            raw[16:], hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        )
    except (ValueError, TypeError):
        return False


def require_user(request: Request):
    token = request.cookies.get("travel_session", "")
    with Session() as db:
        session = db.get(LoginSession, hash_token(token))
        if not session or session.expires < now():
            raise HTTPException(401, "请先登录")
        if not db.get(User, session.owner):
            raise HTTPException(401, "账户已注销")
        if "." in token:
            try:
                claims = jwt.decode(
                    token,
                    signing_key(),
                    algorithms=["HS256"],
                    issuer="travel_agent",
                    audience="travel_agent",
                    options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
                )
                if claims["sub"] != session.owner:
                    raise jwt.InvalidTokenError("owner mismatch")
            except jwt.InvalidTokenError:
                raise HTTPException(401, "登录凭证无效或已过期")
        # Opaque sessions issued before this migration expire naturally; new sessions are JWT.
        profile = db.get(AccountProfile, session.owner)
        if (
            settings.email_required
            and (not profile or not profile.email_verified)
            and request.url.path
            not in {
                "/api/v1/auth/me",
                "/api/v1/auth/logout",
                "/api/v1/auth/resend-verification",
                "/api/v1/privacy/export",
                "/api/v1/privacy/account",
            }
        ):
            raise HTTPException(403, "请先验证邮箱")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(csrf, session.csrf):
                raise HTTPException(403, "页面验证已过期，请重新登录")
        return session.owner


def new_session(db, user, days):
    issued = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": user.id,
            "jti": secrets.token_urlsafe(24),
            "iat": issued,
            "exp": issued + timedelta(days=days),
            "iss": "travel_agent",
            "aud": "travel_agent",
        },
        signing_key(),
        algorithm="HS256",
    )
    csrf = secrets.token_urlsafe(24)
    db.add(
        LoginSession(token=hash_token(token), owner=user.id, csrf=csrf, expires=now() + timedelta(days=days))
    )
    return token, csrf
