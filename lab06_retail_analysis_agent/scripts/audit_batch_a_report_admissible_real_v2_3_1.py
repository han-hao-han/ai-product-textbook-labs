"""Audit the saved V2.3.1 real checkpoint without new model calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.batch_a_report_admissible_real_audit_v2_3_1 import (  # noqa: E402
    run_concentrated_audit,
)


if __name__ == "__main__":
    print(json.dumps(run_concentrated_audit(), ensure_ascii=False, indent=2))
