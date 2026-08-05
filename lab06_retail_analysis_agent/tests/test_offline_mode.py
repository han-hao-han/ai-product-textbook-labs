from __future__ import annotations

import unittest

from src.offline_mode import (
    CapabilityDeniedError,
    build_mode_policy,
    require_capability,
)


class OfflineModeTests(unittest.TestCase):
    def test_no_key_mode_is_explicit_tool_experience(self) -> None:
        policy = build_mode_policy(api_key_configured=False)

        self.assertEqual(policy.user_visible_label, "工具层体验")
        self.assertFalse(policy.may_claim_agent_behavior)
        require_capability(policy, "run_manual_whitelist_tool")

    def test_no_key_mode_rejects_agent_capabilities(self) -> None:
        policy = build_mode_policy(api_key_configured=False)

        for capability in (
            "natural_language_understanding",
            "model_tool_selection",
            "autonomous_multi_tool_calls",
            "multi_turn_conversation",
            "ai_business_report",
        ):
            with self.subTest(capability=capability):
                with self.assertRaises(CapabilityDeniedError):
                    require_capability(policy, capability)

    def test_online_mode_allows_agent_capabilities(self) -> None:
        policy = build_mode_policy(api_key_configured=True)

        self.assertTrue(policy.may_claim_agent_behavior)
        require_capability(policy, "model_tool_selection")


if __name__ == "__main__":
    unittest.main()
