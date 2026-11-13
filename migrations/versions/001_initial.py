"""Initial durable business model. Graph checkpointer manages its own migrations."""

from alembic import op
from travel_agent.db import Base

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
