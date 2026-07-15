#!/usr/bin/env python3
"""Database migration script for wi1-bot."""

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    """Run Alembic database migrations."""
    parser = argparse.ArgumentParser(description="Manage database migrations")
    parser.add_argument(
        "action",
        choices=["upgrade", "downgrade", "current", "history", "revision"],
        help="Migration action to perform",
    )
    parser.add_argument(
        "revision",
        nargs="?",
        default="head",
        help="Target revision (default: head)",
    )
    parser.add_argument(
        "-m",
        "--message",
        help="Message for new revision (only used with 'revision' action)",
    )
    parser.add_argument(
        "--autogenerate",
        action="store_true",
        help="Autogenerate migration from model changes (only used with 'revision' action)",
    )

    args = parser.parse_args()

    # Find alembic.ini in the wi1_bot package
    wi1_bot_dir = Path(__file__).resolve().parent.parent
    alembic_ini = wi1_bot_dir / "alembic.ini"

    if not alembic_ini.exists():
        print(f"Error: alembic.ini not found at {alembic_ini}", file=sys.stderr)
        sys.exit(1)

    alembic_cfg = Config(str(alembic_ini))

    try:
        if args.action == "upgrade":
            command.upgrade(alembic_cfg, args.revision)
            print(f"Database upgraded to {args.revision}")
        elif args.action == "downgrade":
            command.downgrade(alembic_cfg, args.revision)
            print(f"Database downgraded to {args.revision}")
        elif args.action == "current":
            command.current(alembic_cfg)
        elif args.action == "history":
            command.history(alembic_cfg)
        elif args.action == "revision":
            if args.autogenerate:
                command.revision(alembic_cfg, message=args.message, autogenerate=True)
            else:
                command.revision(alembic_cfg, message=args.message)
            print(f"Created new revision: {args.message or 'empty'}")
    except Exception as e:
        print(f"Error running migration: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
