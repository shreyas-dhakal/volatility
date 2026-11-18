"""The auth cleanup removes only sessions, never unmigrated owners or credentials."""

import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_cleanup_preserves_owners_projects_source_ciphertext_and_offline_digests():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)

        def migration(name):
            path = Path(__file__).parents[1] / "alembic" / "versions" / name
            spec = importlib.util.spec_from_file_location("auth_migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.op = Operations(context)
            return module

        migration("af78127a72ed_initial_schema.py").upgrade()
        connection.exec_driver_sql(
            "INSERT INTO users (id,email,name,password_hash,created_at) VALUES ('owner','synthetic@example.com','Synthetic','retained-offline-digest',CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO projects (id,user_id,name,description,system_type,objective,created_at) VALUES ('p','owner','Synthetic','','new','',CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO accounts (id,user_id,github_id,token_ciphertext,created_at) VALUES ('a','owner','123','retained-ciphertext',CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO sessions (id,user_id,token_hash,expires_at,created_at) VALUES ('s','owner','obsolete',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
        migration("8c31d29a40bf_clerk_identity_mapping.py").upgrade()
        cleanup = migration("19d05c88b712_remove_local_auth_sessions.py")
        cleanup.upgrade()
        assert "sessions" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql(
            "SELECT id,password_hash FROM users"
        ).one() == ("owner", "retained-offline-digest")
        assert (
            connection.exec_driver_sql("SELECT user_id FROM projects").scalar()
            == "owner"
        )
        assert connection.exec_driver_sql(
            "SELECT user_id,token_ciphertext FROM accounts"
        ).one() == ("owner", "retained-ciphertext")
        cleanup.downgrade()
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM sessions").scalar() == 0
    engine.dispose()
