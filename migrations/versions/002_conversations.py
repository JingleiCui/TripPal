"""会话、协作与个性化相关的数据表；增量迁移。"""

from alembic import op
from travel_agent.db import TripMember, Conversation, Message, Signal

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    for model in (TripMember, Conversation, Message, Signal):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (Signal, Message, Conversation, TripMember):
        model.__table__.drop(op.get_bind(), checkfirst=True)
