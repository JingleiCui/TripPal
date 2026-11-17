from datetime import datetime, timezone
import uuid
from sqlalchemy import create_engine, String, Text, Integer, JSON, UniqueConstraint, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(256))
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[datetime] = mapped_column(DateTime)


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=0)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("trip_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    plan: Mapped[dict] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("owner", "request_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    lease: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    info: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Share(Base):
    __tablename__ = "shares"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    expires: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[int] = mapped_column(Integer, default=0)


class TripMember(Base):
    __tablename__ = "trip_members"
    __table_args__ = (UniqueConstraint("trip_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    slots: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class Message(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "request_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    owner: Mapped[str] = mapped_column(String(32))
    request_key: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Signal(Base):
    __tablename__ = "preference_signals"
    __table_args__ = (UniqueConstraint("owner", "request_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class AccountProfile(Base):
    __tablename__ = "account_profiles"
    owner: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, unique=True)
    email_verified: Mapped[int] = mapped_column(Integer, default=0)
    consent: Mapped[dict] = mapped_column(JSON, default=dict)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    expires: Mapped[datetime] = mapped_column(DateTime)
    consumed: Mapped[int] = mapped_column(Integer, default=0)


class MailOutbox(Base):
    __tablename__ = "mail_outbox"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class PrivacyCleanup(Base):
    __tablename__ = "privacy_cleanup"
    # This tombstone intentionally survives account deletion, until external cleanup succeeds.
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32))
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(100), default="")


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 5},
)
Session = sessionmaker(engine, expire_on_commit=False)


def event(task_id: str, kind: str, **data):
    with Session.begin() as db:
        task = db.get(Task, task_id)
        if task:
            db.add(
                Event(
                    task_id=task_id,
                    kind=kind,
                    data={**data, "attempt": task.payload.get("execution_attempt", 0)},
                )
            )


class SavedPlace(Base):
    __tablename__ = "saved_places"
    __table_args__ = (UniqueConstraint("owner", "place_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    place_id: Mapped[str] = mapped_column(String(120))
    place: Mapped[dict] = mapped_column(JSON)
    collection: Mapped[str] = mapped_column(String(60), default="旅行心愿单")
    note: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class TravelBooking(Base):
    __tablename__ = "travel_bookings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    details: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class DailyDetailSnapshot(Base):
    __tablename__ = "daily_detail_snapshots"
    __table_args__ = (UniqueConstraint("trip_id", "version", "day", "mode"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    """受治理工具调用的审计记录：谁、在什么范围、调用了什么、结果如何。

    既服务于 MCP server（外部调用），也服务于内部工具治理，使 Agent 的
    每一次对外工具调用都可追溯、可审计。"""

    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(40), default="agent")  # mcp / api / agent / attachment
    scope: Mapped[str] = mapped_column(String(60), default="")
    tool: Mapped[str] = mapped_column(String(60), index=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    success: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class PendingChange(Base):
    """行程变更的可撤销卡片。Agent 提交修改后生成一条待应用卡片，用户在

    撤销窗口（默认 15 分钟）内可一键撤销回到上一版本；窗口过期后卡片淡出，
    但历史版本仍可恢复。比 interrupt 阻塞更顺滑、更具 Agent-native 特质。"""

    __tablename__ = "pending_changes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    trip_id: Mapped[str] = mapped_column(String(32), ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="plan_edit")  # plan_edit / attachment_suggestion
    summary: Mapped[str] = mapped_column(Text, default="")
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    applied_plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending / dismissed
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


class Attachment(Base):
    """用户上传的附件（GPX / 订单文本 / 订单截图）。

    上传即触发解析与 Agent 建议：GPX 提取轨迹与距离，订单文本提取城市/日期/
    订单项，图片在配置视觉模型时尝试 OCR，否则提示手动录入。解析结果持久化，
    供前端呈现「建议动作」。"""

    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    ext: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(20), default="unknown")  # gpx / order / image / unknown
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    suggestion: Mapped[str] = mapped_column(Text, default="")
    created: Mapped[datetime] = mapped_column(DateTime, default=now)


def ensure_tables():
    """在项目启动路径（API lifespan / MCP server）调用，确保新增表已创建。

    幂等；不触碰既有表结构。"""
    Base.metadata.create_all(engine)
