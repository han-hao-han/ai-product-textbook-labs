"""Run the V2.3.4.2 Q02 checkpoint through its offline authorization gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (  # noqa: E402
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.q02_internal_call_arithmetic_guard_v2_3_4_2_runner import (  # noqa: E402
    OFFLINE_CONFIRMATION,
    execute_q02,
    validate_offline_execution_request,
)


def main() -> int:
    authority = validate_offline_execution_request(
        confirmation=OFFLINE_CONFIRMATION
    )
    logical_client = CallIsolatedLogicalClientV2_3_4_2(
        CallIsolatedFrozenQuestionNativeToolMockClient()
    )
    result = execute_q02(
        api_key="offline-evidence-key-not-real",
        registry=FrozenH2MockRegistry(),
        transport=OfflineDeepSeekProviderV2_3_4_2(logical_client),
        authority=authority,
        output_parent=PROJECT_ROOT / "results" / "raw",
    )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
