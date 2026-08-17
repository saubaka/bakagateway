"""Add OAuth application metadata and per-user permissions."""

import sqlalchemy as sa
from alembic import op

revision = "f3c9a1d7e642"
down_revision = "8a4c1f7d2e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=254),
            nullable=True,
        )
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.add_column(
            sa.Column(
                "privacy_policy_url",
                sa.String(length=500),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "icon_url",
                sa.String(length=500),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "requested_scopes",
                sa.String(length=300),
                nullable=False,
                server_default="openid",
            )
        )
    op.execute(
        "UPDATE gateway_clients "
        "SET scopes = 'openid profile email avatar' "
        "WHERE scopes = 'openid profile email'"
    )

    op.create_table(
        "user_client_consents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("granted_scopes", sa.String(length=300), nullable=False),
        sa.Column("denied_scopes", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["gateway_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_id", name="uq_user_client_consent"),
    )
    with op.batch_alter_table("user_client_consents") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_client_consents_client_id"), ["client_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_user_client_consents_user_id"), ["user_id"], unique=False
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO user_client_consents
                (user_id, client_id, granted_scopes, denied_scopes, created_at, updated_at)
            SELECT
                oauth_tokens.user_id,
                oauth_tokens.client_id,
                MAX(oauth_tokens.scope),
                '',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM oauth_tokens
            JOIN gateway_clients
              ON gateway_clients.client_id = oauth_tokens.client_id
            GROUP BY oauth_tokens.user_id, oauth_tokens.client_id
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("user_client_consents") as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_client_consents_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_client_consents_client_id"))
    op.drop_table("user_client_consents")
    with op.batch_alter_table("gateway_clients") as batch_op:
        batch_op.drop_column("requested_scopes")
        batch_op.drop_column("icon_url")
        batch_op.drop_column("privacy_policy_url")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=254),
            nullable=False,
        )
