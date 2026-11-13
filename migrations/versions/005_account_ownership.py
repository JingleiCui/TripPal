from alembic import op
from sqlalchemy import inspect

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("account_profiles", "auth_tokens", "mail_outbox"):
        if not inspect(op.get_bind()).get_foreign_keys(table):
            op.create_foreign_key(
                "fk_" + table + "_owner", table, "users", ["owner"], ["id"], ondelete="CASCADE"
            )


def downgrade():
    for table in ("mail_outbox", "auth_tokens", "account_profiles"):
        op.drop_constraint("fk_" + table + "_owner", table, type_="foreignkey")
