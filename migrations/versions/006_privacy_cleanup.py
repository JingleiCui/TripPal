from alembic import op
from travel_agent.db import PrivacyCleanup

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    PrivacyCleanup.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    PrivacyCleanup.__table__.drop(op.get_bind(), checkfirst=True)
