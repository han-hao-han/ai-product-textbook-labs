from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_controlled_claim_plan_transport_mock_v2_3_3 import (  # noqa: E402
    ControlledClaimPlanLogicalClientV2_3_3,
    OfflineDeepSeekProviderV2_3_3,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient  # noqa: E402
from src.q02_controlled_claim_plan_v2_3_3_runner import (  # noqa: E402
    OFFLINE_CONFIRMATION,
    execute_q02,
    validate_offline_execution_request,
)


if __name__ == "__main__":
    provider = OfflineDeepSeekProviderV2_3_3(
        ControlledClaimPlanLogicalClientV2_3_3(FrozenQuestionNativeToolMockClient())
    )
    result = execute_q02(
        api_key="offline-v233-q02-runner-key",
        registry=FrozenH2MockRegistry(),
        transport=provider,
        authority=validate_offline_execution_request(confirmation=OFFLINE_CONFIRMATION),
        output_parent=PROJECT_ROOT / "results" / "raw",
    )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
