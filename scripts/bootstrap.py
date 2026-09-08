#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base, SessionLocal, engine
from app.models import Organization, OrganizationType, User, UserRole
from app.utils import get_hashed_password


def main():
    parser = argparse.ArgumentParser(description="Bootstrap PlaceAI with the first institution and platform/institution admins.")
    parser.add_argument("--platform-email", required=True)
    parser.add_argument("--platform-username", default="platformadmin")
    parser.add_argument("--platform-password", required=True)
    parser.add_argument("--institution", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-username", default="tpoadmin")
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        platform = db.query(User).filter(User.email == args.platform_email.lower()).first()
        if not platform:
            platform = User(
                email=args.platform_email.lower(),
                username=args.platform_username,
                hashed_password=get_hashed_password(args.platform_password),
                role=UserRole.platform_admin,
                email_verified=True,
            )
            db.add(platform)
            db.flush()

        org = db.query(Organization).filter(Organization.slug == args.slug.lower()).first()
        if not org:
            org = Organization(name=args.institution, slug=args.slug.lower(), organization_type=OrganizationType.institution)
            db.add(org)
            db.flush()

        admin = db.query(User).filter(User.email == args.admin_email.lower()).first()
        if not admin:
            admin = User(
                email=args.admin_email.lower(),
                username=args.admin_username,
                hashed_password=get_hashed_password(args.admin_password),
                role=UserRole.institution_admin,
                organization_id=org.id,
                email_verified=True,
            )
            db.add(admin)
        db.commit()
        print(f"Bootstrap complete. Institution code: {org.slug}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
