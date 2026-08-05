"""Run the formal V2.3.3 controlled claim-plan offline validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.controlled_claim_plan_validation_v2_3_3 import run_offline_validation  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(run_offline_validation(), ensure_ascii=False, indent=2))
