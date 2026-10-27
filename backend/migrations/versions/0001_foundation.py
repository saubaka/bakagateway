"""Installation baseline; deliberately creates no accounts or passwords."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "platform_installation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schema_label", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.bulk_insert(table, [{"id": 1, "schema_label": "p1-foundation"}])


def downgrade():
    op.drop_table("platform_installation")
