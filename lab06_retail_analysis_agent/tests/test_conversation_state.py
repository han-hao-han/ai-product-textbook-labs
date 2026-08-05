from __future__ import annotations

import unittest

from src.conversation_state import (
    ConditionOperation,
    EffectiveConditions,
    StateTransitionError,
    resolve_conditions,
)


class ConversationStateTests(unittest.TestCase):
    def test_added_inherited_modified_and_removed_are_distinct(self) -> None:
        first = resolve_conditions(
            EffectiveConditions.empty(),
            [
                ConditionOperation(
                    field="metric",
                    operation="set",
                    value="sales_amount",
                ),
                ConditionOperation(
                    field="top_n",
                    operation="set",
                    value=3,
                ),
            ],
        )
        second = resolve_conditions(
            first.effective,
            [
                ConditionOperation(
                    field="top_n",
                    operation="set",
                    value=5,
                ),
            ],
        )
        third = resolve_conditions(
            second.effective,
            [
                ConditionOperation(
                    field="top_n",
                    operation="remove",
                    value=None,
                ),
            ],
        )

        self.assertEqual(
            {change.field: change.status for change in first.changes},
            {"metric": "added", "top_n": "added"},
        )
        self.assertEqual(
            {change.field: change.status for change in second.changes},
            {"metric": "inherited", "top_n": "modified"},
        )
        self.assertEqual(
            {change.field: change.status for change in third.changes},
            {"metric": "inherited", "top_n": "removed"},
        )

    def test_duplicate_field_operations_are_rejected(self) -> None:
        with self.assertRaises(StateTransitionError):
            resolve_conditions(
                EffectiveConditions.empty(),
                [
                    ConditionOperation(
                        field="metric",
                        operation="set",
                        value="sales_amount",
                    ),
                    ConditionOperation(
                        field="metric",
                        operation="set",
                        value="order_count",
                    ),
                ],
            )

    def test_removing_absent_condition_is_rejected(self) -> None:
        with self.assertRaises(StateTransitionError):
            resolve_conditions(
                EffectiveConditions.empty(),
                [
                    ConditionOperation(
                        field="filters",
                        operation="remove",
                        value=None,
                    )
                ],
            )

    def test_custom_date_range_is_validated(self) -> None:
        with self.assertRaises(StateTransitionError):
            resolve_conditions(
                EffectiveConditions.empty(),
                [
                    ConditionOperation(
                        field="time_range",
                        operation="set",
                        value={
                            "mode": "custom",
                            "start_date": "2011-12-02",
                            "end_date": "2011-12-01",
                        },
                    )
                ],
            )


if __name__ == "__main__":
    unittest.main()
