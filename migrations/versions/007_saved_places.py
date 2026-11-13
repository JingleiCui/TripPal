from alembic import op
from travel_agent.db import SavedPlace

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    SavedPlace.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    SavedPlace.__table__.drop(op.get_bind(), checkfirst=True)
