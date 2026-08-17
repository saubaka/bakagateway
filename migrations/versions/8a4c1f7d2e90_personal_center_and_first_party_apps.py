"""Add personal-center avatars and first-party application returns."""

import sqlalchemy as sa
from alembic import op

revision = "8a4c1f7d2e90"
down_revision = "27e943913ba6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("avatar_filename", sa.String(length=255)))
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_first_party",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.drop_column("is_first_party")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("avatar_filename")
