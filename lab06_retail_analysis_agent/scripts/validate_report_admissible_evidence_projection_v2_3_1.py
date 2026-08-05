"""Run the V2.3.1 report-admissible evidence offline validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.report_admissible_evidence_projection_validation_v2_3_1 import (  # noqa: E402
    run_offline_validation,
)


if __name__ == "__main__":
    print(json.dumps(run_offline_validation(), ensure_ascii=False, indent=2))
