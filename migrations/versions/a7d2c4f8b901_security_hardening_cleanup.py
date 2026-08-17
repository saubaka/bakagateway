"""Remove unsafe one-time links and unused authentication fields."""

import sqlalchemy as sa
from alembic import op

revision = "a7d2c4f8b901"
down_revision = "f3c9a1d7e642"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("one_time_tokens")
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_column("fingerprint")
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.drop_column("is_first_party")


def downgrade() -> None:
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_first_party",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "fingerprint",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )
    op.create_table(
        "one_time_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("one_time_tokens") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_one_time_tokens_purpose"),
            ["purpose"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_one_time_tokens_token_hash"),
            ["token_hash"],
            unique=True,
        )
