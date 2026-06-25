#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_server.services.invite_code_service import current_invite_code


def main() -> int:
    print(current_invite_code())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
