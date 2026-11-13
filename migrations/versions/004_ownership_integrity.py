"""Ownership FKs prevent writes racing account deletion; fail on orphaned old data."""

from alembic import op
from sqlalchemy import inspect, text
from travel_agent.db import Base

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        existing = {tuple(f["constrained_columns"]) for f in inspect(bind).get_foreign_keys(table.name)}
        for constraint in table.foreign_key_constraints:
            element = list(constraint.elements)[0]
            column = element.parent.name
            target = element.column.table.name
            target_column = element.column.name
            if (column,) in existing:
                continue
            # All identifiers come from metadata, never user text.
            count = bind.execute(
                text(
                    f"SELECT COUNT(*) FROM `{table.name}` c LEFT JOIN `{target}` p ON c.`{column}`=p.`{target_column}` WHERE c.`{column}` IS NOT NULL AND p.`{target_column}` IS NULL"
                )
            ).scalar()
            if count:
                raise RuntimeError(f"{table.name} 存在 {count} 条孤立记录，未自动删除数据，请先核对")
            op.create_foreign_key(
                "fk_" + table.name + "_" + column,
                table.name,
                target,
                [column],
                [target_column],
                ondelete=constraint.ondelete,
            )


def downgrade():
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        for f in inspect(bind).get_foreign_keys(table.name):
            if f["name"].startswith("fk_"):
                op.drop_constraint(f["name"], table.name, type_="foreignkey")
