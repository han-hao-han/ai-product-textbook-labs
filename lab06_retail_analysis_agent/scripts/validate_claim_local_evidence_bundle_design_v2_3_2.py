"""Validate the V2.3.2 design without implementing or calling a model."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.claim_local_evidence_bundle_design_v2_3_2 import (  # noqa: E402
    validate_design,
)


if __name__ == "__main__":
    print(json.dumps(asdict(validate_design()), ensure_ascii=False, indent=2))
