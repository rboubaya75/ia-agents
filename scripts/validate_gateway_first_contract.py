#!/usr/bin/env python3
"""Deprecated compatibility wrapper.

Use ``scripts/validate_secure_facade_contract.py``. This filename remains only
until all external workflow references have migrated.
"""

from validate_secure_facade_contract import main


if __name__ == "__main__":
    raise SystemExit(main())
