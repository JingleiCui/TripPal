from alembic import op
from travel_agent.db import AccountProfile, AuthToken, MailOutbox

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    for model in (AccountProfile, AuthToken, MailOutbox):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (MailOutbox, AuthToken, AccountProfile):
        model.__table__.drop(op.get_bind(), checkfirst=True)
