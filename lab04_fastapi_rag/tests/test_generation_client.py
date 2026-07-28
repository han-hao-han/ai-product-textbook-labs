from __future__ import annotations

from types import SimpleNamespace

from src.generation_client import (
    AliyunGenerationClient,
    CompletionRecord,
    prepare_generation_client,
    read_generation_state,
)
from src.generation_config import load_generation_config
from src.generation_schemas import (
    QuestionClassification,
    QuestionType,
    RagAnswer,
)


class _FakeCompletions:
    def __init__(self, contents: list[str]) -> None:
        self.contents = list(contents)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0)
        return SimpleNamespace(
            id="response-id",
            model="qwen3.7-plus-2026-05-26",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                model_dump=lambda: {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                }
            ),
        )


class _FakeOpenAI:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def test_openai_request_uses_json_mode_without_token_cap() -> None:
    config = load_generation_config()
    completions = _FakeCompletions(
        ['{"question_type":"concise_concept"}']
    )
    client = AliyunGenerationClient(
        config,
        "secret-not-saved",
        client_factory=lambda **_: _FakeOpenAI(completions),
    )

    parsed, _ = client.classify("什么是FastAPI？")

    assert parsed.question_type == QuestionType.concise_concept
    call = completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"enable_thinking": False}
    assert call["stream"] is False
    assert call["temperature"] == 0
    assert "max_tokens" not in call
    assert "max_completion_tokens" not in call


def test_missing_key_creates_retrieval_only_without_online_call(
    tmp_path,
) -> None:
    config = load_generation_config()

    result = prepare_generation_client(
        tmp_path,
        config,
        environment={},
        backend_factory=lambda *_: (_ for _ in ()).throw(
            AssertionError("backend must not be created")
        ),
    )

    assert result["status"] == "retrieval_only"
    assert result["online_model_called"] is False
    assert result["api_key_saved"] is False
    assert read_generation_state(tmp_path)["status"] == "retrieval_only"


class _PassingBackend:
    def classify(self, question):
        return (
            QuestionClassification(
                question_type=QuestionType.concise_concept
            ),
            CompletionRecord(
                "classification",
                '{"question_type":"concise_concept"}',
                "id1",
                "model",
                "stop",
                None,
                1,
                0.1,
            ),
        )

    def answer(self, question, question_type, hits):
        return (
            RagAnswer(
                answerable=True,
                answer="使用HTTPException。",
                cited_chunk_ids=["probe_chunk_001"],
                refusal_reason=None,
            ),
            CompletionRecord(
                "answer",
                '{"answerable":true}',
                "id2",
                "model",
                "stop",
                None,
                1,
                0.1,
            ),
            [],
        )


def test_successful_probe_marks_passed_but_never_saves_key(tmp_path) -> None:
    config = load_generation_config()

    result = prepare_generation_client(
        tmp_path,
        config,
        environment={"DASHSCOPE_API_KEY": "secret-not-saved"},
        backend_factory=lambda *_: _PassingBackend(),
    )
    persisted = (
        tmp_path
        / "generation"
        / "attempts"
        / "attempt_001"
        / "preparation.json"
    ).read_text(encoding="utf-8")

    assert result["status"] == "passed"
    assert result["online_model_called"] is True
    assert "secret-not-saved" not in persisted
    assert read_generation_state(tmp_path)["status"] == "passed"
