"""Run the formal V2.3 report-terminal serialization validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_report_terminal_serialization_v2_3 import (  # noqa: E402
    run_offline_validation,
)


if __name__ == "__main__":
    print(
        json.dumps(
            run_offline_validation(),
            ensure_ascii=False,
            indent=2,
        )
    )
