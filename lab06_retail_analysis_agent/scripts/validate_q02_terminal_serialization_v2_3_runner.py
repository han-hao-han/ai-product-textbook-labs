"""Persist the offline Q02 V2.3 safe-runner validation evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_report_terminal_transport_mock_v2_3 import (  # noqa: E402
    FrozenNativeLogicalClientV2_3,
    OfflineDeepSeekProviderV2_3,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.q01_q10_batch_a_offline_mock import (  # noqa: E402
    BatchAEvidenceCompleteMockClient,
)
from src.q02_terminal_serialization_v2_3_runner import (  # noqa: E402
    OFFLINE_CONFIRMATION,
    execute_q02_validation,
    validate_offline_execution_request,
)


if __name__ == "__main__":
    provider = OfflineDeepSeekProviderV2_3(
        FrozenNativeLogicalClientV2_3(BatchAEvidenceCompleteMockClient())
    )
    result = execute_q02_validation(
        api_key="offline-q02-v2-3-runner-validation-secret",
        registry=FrozenH2MockRegistry(),
        transport=provider,
        authority=validate_offline_execution_request(
            confirmation=OFFLINE_CONFIRMATION
        ),
        output_parent=PROJECT_ROOT / "results" / "raw",
    )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.passed else 1)
