from __future__ import annotations

from typing import Any

from src.generation_client import CompletionRecord, StructuredResponseError
from src.generation_schemas import (
    QuestionClassification,
    QuestionType,
    RagAnswer,
)
from src.io_utils import write_json_atomic
from src.rag_pipeline import run_rag_query


def _prepare_run(tmp_path):
    write_json_atomic(
        tmp_path / "manifest.json",
        {
            "experiment_run_id": tmp_path.name,
            "source_commit": "82064857539e6286522c347b4b11331b48dd2378",
            "frozen_device": "cpu",
        },
    )
    write_json_atomic(
        tmp_path / "index" / "current" / "index_manifest.json",
        {
            "corpus_sha256": (
                "71cf57bca05ddbc43a61a6155690f5bd4ebc07cc1cf6f181fe80bfc2d66e741d"
            ),
            "embeddings_sha256": (
                "250ddaea4e54c67d0de36af64afe66667794d3c0100ecf73706e1ad115262909"
            ),
            "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        },
    )
    return tmp_path


def _hit(chunk_id: str = "chunk_1") -> dict[str, Any]:
    return {
        "rank": 1,
        "score": 0.9,
        "row_index": 0,
        "chunk_id": chunk_id,
        "page_title": "处理错误",
        "section_path": ["HTTPException"],
        "section_paths": [["HTTPException"]],
        "source_path": "docs/zh/docs/tutorial/handling-errors.md",
        "source_url": (
            "https://github.com/fastapi/fastapi/blob/"
            "82064857539e6286522c347b4b11331b48dd2378/"
            "docs/zh/docs/tutorial/handling-errors.md"
        ),
        "chunk_index": 0,
        "token_count": 600,
        "contains_code": True,
        "contains_table": False,
        "content_sha256": "a" * 64,
        "content": (
            "资源不存在时，应当raise HTTPException并设置status_code=404"
            "和detail。"
        )
        * 8,
    }


def _retrieval(score: float):
    def retrieve(*args, **kwargs):
        hit = _hit()
        hit["score"] = score
        return {
            "status": "passed",
            "query": args[3],
            "top_k": kwargs["top_k"],
            "top1_score": score,
            "hits": [hit],
            "query_embedding_diagnostics": {
                "input_count": 1,
                "max_input_tokens": 20,
            },
        }

    return retrieve


def _record(purpose: str, content: str) -> CompletionRecord:
    return CompletionRecord(
        purpose,
        content,
        "id",
        "model",
        "stop",
        None,
        1,
        0.01,
    )


class _AnsweringBackend:
    def classify(self, question):
        return (
            QuestionClassification(question_type=QuestionType.procedure),
            _record("classification", '{"question_type":"procedure"}'),
        )

    def answer(self, question, question_type, hits):
        return (
            RagAnswer(
                answerable=True,
                answer="使用 `raise HTTPException(status_code=404)`。",
                cited_chunk_ids=["chunk_1"],
                refusal_reason=None,
            ),
            _record("answer", '{"answerable":true}'),
            [{"chunk_id": "chunk_1"}],
        )


class _NeverCalledBackend:
    def classify(self, question):
        raise AssertionError("classification must not be called")

    def answer(self, question, question_type, hits):
        raise AssertionError("answer must not be called")


def test_gate_rejection_never_calls_generation(tmp_path) -> None:
    run_dir = _prepare_run(tmp_path)

    result = run_rag_query(
        run_dir,
        "明天北京天气如何？",
        retrieval_function=_retrieval(0.2),
        generation_backend=_NeverCalledBackend(),
    )

    assert result["final_state"] == "retrieval_rejected"
    assert result["generation"]["online_model_called"] is False


def test_gate_pass_without_prepared_client_is_retrieval_only(
    tmp_path,
) -> None:
    run_dir = _prepare_run(tmp_path)

    result = run_rag_query(
        run_dir,
        "如何处理404？",
        retrieval_function=_retrieval(0.9),
        environment={},
    )

    assert result["final_state"] == "retrieval_only"
    assert result["generation"]["online_model_called"] is False


def test_answered_result_has_program_generated_citation(tmp_path) -> None:
    run_dir = _prepare_run(tmp_path)

    result = run_rag_query(
        run_dir,
        "如何处理404？",
        retrieval_function=_retrieval(0.9),
        generation_backend=_AnsweringBackend(),
    )

    assert result["final_state"] == "answered"
    assert result["classification"]["question_type"] == "procedure"
    assert result["citations"][0]["chunk_id"] == "chunk_1"
    assert result["citations"][0]["source_url"].startswith(
        "https://github.com/fastapi/fastapi/blob/"
    )
    assert result["generation"]["online_model_called"] is True


class _RefusingBackend(_AnsweringBackend):
    def answer(self, question, question_type, hits):
        return (
            RagAnswer(
                answerable=False,
                answer=None,
                cited_chunk_ids=[],
                refusal_reason="证据不足，无法回答完整实现。",
            ),
            _record("answer", '{"answerable":false}'),
            [],
        )


def test_model_refusal_is_distinct_from_gate_rejection(tmp_path) -> None:
    result = run_rag_query(
        _prepare_run(tmp_path),
        "如何完整实现高级功能？",
        retrieval_function=_retrieval(0.9),
        generation_backend=_RefusingBackend(),
    )

    assert result["final_state"] == "model_refused"
    assert result["citations"] == []


class _BadCitationBackend(_AnsweringBackend):
    def answer(self, question, question_type, hits):
        return (
            RagAnswer(
                answerable=True,
                answer="不受支持的回答。",
                cited_chunk_ids=["outside_top_k"],
                refusal_reason=None,
            ),
            _record("answer", '{"answerable":true}'),
            [],
        )


def test_out_of_top_k_citation_becomes_validation_failed(tmp_path) -> None:
    result = run_rag_query(
        _prepare_run(tmp_path),
        "问题",
        retrieval_function=_retrieval(0.9),
        generation_backend=_BadCitationBackend(),
    )

    assert result["final_state"] == "validation_failed"
    assert "证据之外" in result["generation"]["error"]


class _ClassificationFallbackBackend(_AnsweringBackend):
    received_type = None

    def classify(self, question):
        raise StructuredResponseError(
            "invalid classification",
            record=_record("classification", "{}"),
        )

    def answer(self, question, question_type, hits):
        self.received_type = question_type
        return super().answer(question, question_type, hits)


def test_classification_failure_falls_back_and_still_answers(
    tmp_path,
) -> None:
    backend = _ClassificationFallbackBackend()

    result = run_rag_query(
        _prepare_run(tmp_path),
        "问题",
        retrieval_function=_retrieval(0.9),
        generation_backend=backend,
    )

    assert result["final_state"] == "answered"
    assert backend.received_type == "comprehensive"
    assert result["classification"]["fallback"] is True
