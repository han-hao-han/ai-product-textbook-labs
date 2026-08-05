from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.run_record import (
    FailureRecord,
    RunRecordError,
    ToolCallRecord,
    TurnRunRecord,
    load_session_run_record,
    save_session_run_record,
    validate_record_security,
)
from src.safe_export import EXPORT_FILENAMES, export_session_bundle
from tests.run_record_fixtures import build_sample_session_record


class RunRecordAndExportTests(unittest.TestCase):
    def test_record_round_trip_and_four_file_export(self) -> None:
        record = build_sample_session_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            local_record = root / "run_record.local.json"
            save_session_run_record(record, local_record)
            loaded = load_session_run_record(local_record)
            paths = export_session_bundle(
                loaded,
                root / "export",
                current_turn_id="TURN-001",
            )

            self.assertEqual(loaded, record)
            self.assertEqual(
                tuple(path.name for path in paths),
                EXPORT_FILENAMES,
            )
            self.assertTrue(all(path.is_file() for path in paths))
            self.assertNotIn(
                "12345",
                (root / "export" / "facts.csv").read_text(
                    encoding="utf-8"
                ),
            )

    def test_export_never_overwrites_existing_target(self) -> None:
        record = build_sample_session_record()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "export"
            output.mkdir()
            (output / "run_record.json").write_text(
                "keep",
                encoding="utf-8",
            )

            with self.assertRaises(RunRecordError):
                export_session_bundle(
                    record,
                    output,
                    current_turn_id="TURN-001",
                )
            self.assertEqual(
                (output / "run_record.json").read_text(
                    encoding="utf-8"
                ),
                "keep",
            )

    def test_sensitive_text_in_record_is_rejected(self) -> None:
        record = build_sample_session_record()
        record.turns[0].original_question = (
            "Authorization: Bearer secret-value"
        )

        with self.assertRaises(RunRecordError):
            validate_record_security(record)

    def test_absolute_path_in_record_is_rejected(self) -> None:
        record = build_sample_session_record()
        record.turns[0].original_question = (
            "请读取D:\\private\\source.xlsx"
        )

        with self.assertRaises(RunRecordError):
            validate_record_security(record)

    def test_failed_call_stage_survives_round_trip(self) -> None:
        record = build_sample_session_record()
        failed_call = ToolCallRecord(
            call_id="CALL-002",
            analysis_target="非法工具验证",
            reason_summary="验证失败记录不会丢失。",
            tool_name="run_python",
            arguments={},
            model_selected=True,
            status="rejected",
            result_path=None,
            error_stage="tool_name",
            error_message="工具不在白名单中。",
        )
        failure = FailureRecord(
            failure_id="FAIL-001",
            call_id="CALL-002",
            stage="tool_name",
            error_type="ToolExecutionError",
            message="工具不在白名单中。",
            raw_response_path=(
                "results/raw/test/failed/FAIL-001/response.json"
            ),
        )
        record.turns[0].tool_calls.append(failed_call)
        record.turns[0].failures.append(failure)

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run_record.json"
            save_session_run_record(record, path)
            loaded = load_session_run_record(path)

        self.assertEqual(
            loaded.turns[0].failures[0].stage,
            "tool_name",
        )
        self.assertEqual(
            loaded.turns[0].tool_calls[1].status,
            "rejected",
        )

    def test_offline_turn_cannot_contain_ai_report(self) -> None:
        record = build_sample_session_record()
        payload = record.turns[0].model_dump(mode="json")
        payload["execution_mode"] = "offline_tool_experience"

        with self.assertRaises(ValidationError):
            TurnRunRecord.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
