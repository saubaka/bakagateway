"""Enforce that active gateway users always have an active administrator."""

from alembic import op

revision = "d4e8a6b2c713"
down_revision = "a7d2c4f8b901"
branch_labels = None
depends_on = None


TRIGGERS = {
    "cloudgate_active_user_requires_administrator_insert": """
        CREATE TRIGGER cloudgate_active_user_requires_administrator_insert
        BEFORE INSERT ON users
        WHEN NEW.status = 'active'
          AND NOT EXISTS (
            SELECT 1
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            WHERE u.status = 'active' AND r.name = 'administrator'
          )
        BEGIN
          SELECT RAISE(ABORT, 'active user requires an active administrator');
        END
    """,
    "cloudgate_active_user_requires_administrator_update": """
        CREATE TRIGGER cloudgate_active_user_requires_administrator_update
        BEFORE UPDATE OF status ON users
        WHEN NEW.status = 'active'
          AND OLD.status <> 'active'
          AND NOT EXISTS (
            SELECT 1
            FROM user_roles AS own_roles
            JOIN roles AS own_role ON own_role.id = own_roles.role_id
            WHERE own_roles.user_id = NEW.id
              AND own_role.name = 'administrator'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            WHERE u.status = 'active' AND r.name = 'administrator'
          )
        BEGIN
          SELECT RAISE(ABORT, 'active user requires an active administrator');
        END
    """,
    "cloudgate_last_administrator_user_delete": """
        CREATE TRIGGER cloudgate_last_administrator_user_delete
        BEFORE DELETE ON users
        WHEN OLD.status = 'active'
          AND EXISTS (
            SELECT 1
            FROM user_roles AS own_roles
            JOIN roles AS own_role ON own_role.id = own_roles.role_id
            WHERE own_roles.user_id = OLD.id
              AND own_role.name = 'administrator'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            WHERE u.id <> OLD.id
              AND u.status = 'active'
              AND r.name = 'administrator'
          )
        BEGIN
          SELECT RAISE(ABORT, 'cannot delete the last active administrator');
        END
    """,
    "cloudgate_last_administrator_status_update": """
        CREATE TRIGGER cloudgate_last_administrator_status_update
        BEFORE UPDATE OF status ON users
        WHEN OLD.status = 'active'
          AND NEW.status <> 'active'
          AND EXISTS (
            SELECT 1
            FROM user_roles AS own_roles
            JOIN roles AS own_role ON own_role.id = own_roles.role_id
            WHERE own_roles.user_id = OLD.id
              AND own_role.name = 'administrator'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            WHERE u.id <> OLD.id
              AND u.status = 'active'
              AND r.name = 'administrator'
          )
        BEGIN
          SELECT RAISE(ABORT, 'cannot disable the last active administrator');
        END
    """,
    "cloudgate_last_administrator_role_delete": """
        CREATE TRIGGER cloudgate_last_administrator_role_delete
        BEFORE DELETE ON user_roles
        WHEN EXISTS (
            SELECT 1 FROM roles
            WHERE roles.id = OLD.role_id AND roles.name = 'administrator'
          )
          AND EXISTS (
            SELECT 1 FROM users
            WHERE users.id = OLD.user_id AND users.status = 'active'
          )
          AND NOT EXISTS (
            SELECT 1
            FROM users AS u
            JOIN user_roles AS ur ON ur.user_id = u.id
            JOIN roles AS r ON r.id = ur.role_id
            WHERE u.id <> OLD.user_id
              AND u.status = 'active'
              AND r.name = 'administrator'
          )
        BEGIN
          SELECT RAISE(ABORT, 'cannot remove the last active administrator role');
        END
    """,
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    for statement in TRIGGERS.values():
        op.execute(statement)


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    for name in reversed(TRIGGERS):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
