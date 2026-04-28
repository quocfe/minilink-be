#!/usr/bin/env python3
"""
Database management script for MiniLink URL Shortener
"""
import asyncio
import sys
from alembic.config import Config
from alembic import command
from src.database import engine, Base
from src.auth.models import User  # noqa: F401 – ensure models are registered
from src.urls.models import URL, ClickEvent  # noqa: F401


async def create_tables():
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created successfully")


async def drop_tables():
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("✅ Database tables dropped successfully")


def run_migrations():
    """Run Alembic migrations."""
    alembic_cfg = Config("alembic.ini")
    try:
        command.upgrade(alembic_cfg, "head")
        print("✅ Database migrations completed successfully")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)


def create_migration(message: str):
    """Create a new migration."""
    alembic_cfg = Config("alembic.ini")
    try:
        command.revision(alembic_cfg, message=message, autogenerate=True)
        print(f"✅ Migration '{message}' created successfully")
    except Exception as e:
        print(f"❌ Migration creation failed: {e}")
        sys.exit(1)


def stamp_migration(revision: str):
    """Stamp the database with a specific revision."""
    alembic_cfg = Config("alembic.ini")
    try:
        command.stamp(alembic_cfg, revision)
        print(f"✅ Database stamped with revision '{revision}' successfully")
    except Exception as e:
        print(f"❌ Stamping failed: {e}")
        sys.exit(1)


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python db_manager.py [create|drop|migrate|makemigration|stamp]")
        print("  create         - Create all tables")
        print("  drop           - Drop all tables")
        print("  migrate        - Run migrations")
        print("  makemigration  - Create new migration (requires message)")
        print("  stamp          - Stamp database with revision (requires revision)")
        sys.exit(1)

    command_arg = sys.argv[1]

    if command_arg == "create":
        asyncio.run(create_tables())
    elif command_arg == "drop":
        asyncio.run(drop_tables())
    elif command_arg == "migrate":
        run_migrations()
    elif command_arg == "makemigration":
        if len(sys.argv) < 3:
            print("Please provide a migration message")
            sys.exit(1)
        message = " ".join(sys.argv[2:])
        create_migration(message)
    elif command_arg == "stamp":
        if len(sys.argv) < 3:
            print("Please provide a revision ID (e.g., 'head' or a specific hash)")
            sys.exit(1)
        revision = sys.argv[2]
        stamp_migration(revision)
    else:
        print(f"Unknown command: {command_arg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
