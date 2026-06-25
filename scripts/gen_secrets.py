"""Generate strong random secrets for the production .env.

Usage:
    python scripts/gen_secrets.py

Prints JWT_SECRET (64 hex chars) and AUTH_PASSWORD (24 URL-safe chars).
Copy the two lines into your .env. The script never writes to disk.
"""
from __future__ import annotations

import secrets


def main() -> None:
    jwt_secret = secrets.token_hex(32)
    auth_password = secrets.token_urlsafe(18)

    print("# Paste the two lines below into your .env (production):")
    print()
    print(f"JWT_SECRET={jwt_secret}")
    print(f"AUTH_PASSWORD={auth_password}")
    print()
    print("# Keep these out of git. Rotate JWT_SECRET will invalidate all existing tokens.")


if __name__ == "__main__":
    main()
