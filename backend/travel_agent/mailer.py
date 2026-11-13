"""Local SMTP outbox. No real mailbox is contacted by the default configuration."""

import secrets
import smtplib
from email.message import EmailMessage
from datetime import timedelta
from sqlalchemy import select
from .db import Session, AccountProfile, AuthToken, MailOutbox, now
from .config import settings


def queue_token(db, owner, purpose):
    from .security import hash_token

    profile = db.get(AccountProfile, owner)
    if not profile or not profile.email:
        return False
    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            token=hash_token(token), owner=owner, purpose=purpose, expires=now() + timedelta(minutes=30)
        )
    )
    path = "/verify-email" if purpose == "verify" else "/reset-password"
    url = settings.public_base_url.rstrip("/") + path + "#token=" + token
    db.add(
        MailOutbox(
            owner=owner,
            recipient=profile.email,
            subject="travel_agent · " + ("验证邮箱" if purpose == "verify" else "重置密码"),
            body="请通过以下链接"
            + ("验证邮箱" if purpose == "verify" else "设置新密码")
            + "。链接 30 分钟有效且仅能使用一次。\n\n"
            + url,
        )
    )
    return True


def deliver_pending():
    if not settings.smtp_allow_external and settings.smtp_host not in {"127.0.0.1", "localhost", "mailpit"}:
        return
    with Session.begin() as db:
        rows = db.scalars(
            select(MailOutbox)
            .where(MailOutbox.status == "queued")
            .order_by(MailOutbox.created)
            .limit(5)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            message = EmailMessage()
            message["From"] = settings.mail_from
            message["To"] = row.recipient
            message["Subject"] = row.subject
            message.set_content(row.body)
            try:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as client:
                    if settings.smtp_starttls:
                        client.starttls()
                    if settings.smtp_user:
                        client.login(settings.smtp_user, settings.smtp_password)
                    client.send_message(message)
                row.status = "sent"
                row.body = "[令牌邮件已投递，正文已清除]"
            except (OSError, smtplib.SMTPException):
                # Unknown SMTP delivery may duplicate a token email, never create a second token action.
                continue
