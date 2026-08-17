"""Add the administrator-managed application service-policy URL."""

import sqlalchemy as sa
from alembic import op

revision = "e6f1b9c4d802"
down_revision = "d4e8a6b2c713"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.add_column(
            sa.Column(
                "service_terms_url",
                sa.String(length=500),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.drop_column("service_terms_url")
