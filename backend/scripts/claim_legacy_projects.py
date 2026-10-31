from __future__ import annotations

import argparse
import uuid

from app.database import SessionLocal
from app.services.legacy_ownership import claim_legacy_projects


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign explicitly named legacy projects to one verified Supabase Auth user."
    )
    parser.add_argument("--user-id", required=True, type=uuid.UUID)
    parser.add_argument("--project-id", required=True, action="append", type=uuid.UUID)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the transaction is rolled back.",
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        claimed = claim_legacy_projects(db, args.user_id, args.project_id)
        if args.apply:
            db.commit()
            print(f"Claimed {claimed} project(s) for {args.user_id}.")
        else:
            db.rollback()
            print(f"Dry run: {claimed} project(s) can be claimed; no changes were saved.")


if __name__ == "__main__":
    main()
