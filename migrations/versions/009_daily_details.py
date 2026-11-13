from alembic import op
from travel_agent.db import DailyDetailSnapshot

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    DailyDetailSnapshot.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    DailyDetailSnapshot.__table__.drop(op.get_bind(), checkfirst=True)
