"""Run formal V2.3.2 bundle validation without real model calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.claim_evidence_bundle_validation_v2_3_2 import (  # noqa: E402
    run_offline_validation,
)


if __name__ == "__main__":
    print(json.dumps(run_offline_validation(), ensure_ascii=False, indent=2))
