from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.deepseek_report_terminal_transport_mock_v2_3_2 import (
    BundleAwareLogicalClientV2_3_2,
    OfflineDeepSeekProviderV2_3_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.q02_claim_evidence_bundle_v2_3_2_runner import (
    OFFLINE_CONFIRMATION,
    REAL_CONFIRMATION,
    Q02ClaimEvidenceV2_3_2RunnerError,
    Q02ExecutionAuthorityV2_3_2,
    consume_real_authority,
    execute_q02_validation,
    validate_offline_execution_request,
    validate_real_execution_request,
)


class Q02ClaimEvidenceBundleV2_3_2RunnerTests(unittest.TestCase):
    def test_offline_success_has_two_responses_and_v2_3_2_bundle(self) -> None:
        provider = OfflineDeepSeekProviderV2_3_2(
            BundleAwareLogicalClientV2_3_2(FrozenQuestionNativeToolMockClient())
        )
        authority = validate_offline_execution_request(confirmation=OFFLINE_CONFIRMATION)
        with tempfile.TemporaryDirectory() as temporary:
            result = execute_q02_validation(
                api_key="offline-v232-secret",
                registry=FrozenH2MockRegistry(),
                transport=provider,
                authority=authority,
                output_parent=Path(temporary),
                run_id="offline-q02-v232-success",
            )
            evidence = (result.output_dir / "Q02.json").read_text(encoding="utf-8")
        self.assertTrue(result.passed, result.summary)
        self.assertEqual(result.summary["actual_response_attempts"], 2)
        self.assertEqual(result.summary["claim_evidence_bundle_version"], "v2.3.2")
        self.assertFalse(result.summary["authorization_consumed"])
        self.assertNotIn("offline-v232-secret", evidence)

    def test_real_authority_consumption_is_single_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = Q02ExecutionAuthorityV2_3_2(
                mode="real_transport", authorization_id="v232-unit-single-use"
            )
            self.assertTrue(consume_real_authority(authority, consumption_root=root).exists())
            with self.assertRaisesRegex(Q02ClaimEvidenceV2_3_2RunnerError, "already consumed"):
                consume_real_authority(authority, consumption_root=root)

    def test_consumed_project_authority_and_wrong_scope_are_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                Q02ClaimEvidenceV2_3_2RunnerError,
                "no exact unconsumed",
            ):
                validate_real_execution_request(
                    question_id="Q02",
                    model="deepseek-v4-flash",
                    approved_model_responses=2,
                    automatic_retries=0,
                    confirmation=REAL_CONFIRMATION,
                    consumption_root=root,
                )
            with self.assertRaisesRegex(
                Q02ClaimEvidenceV2_3_2RunnerError,
                "only Q02",
            ):
                validate_real_execution_request(
                    question_id="Q06",
                    model="deepseek-v4-flash",
                    approved_model_responses=2,
                    automatic_retries=0,
                    confirmation=REAL_CONFIRMATION,
                    consumption_root=root,
                )


if __name__ == "__main__":
    unittest.main()
