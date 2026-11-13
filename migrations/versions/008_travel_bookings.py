from alembic import op
from travel_agent.db import TravelBooking

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    TravelBooking.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    TravelBooking.__table__.drop(op.get_bind(), checkfirst=True)
