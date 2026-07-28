from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "source_config.json"
EMBEDDING_CONFIG_PATH = PROJECT_ROOT / "configs" / "embedding_config.json"
GENERATION_CONFIG_PATH = PROJECT_ROOT / "configs" / "generation_config.json"
JUDGE_CONFIG_PATH = PROJECT_ROOT / "configs" / "judge_config.json"
JUDGE_OUTPUT_SCHEMA_PATH = (
    PROJECT_ROOT / "configs" / "judge_output.schema.json"
)
CALIBRATION_QUESTIONS_PATH = (
    PROJECT_ROOT / "configs" / "calibration_questions_candidate.json"
)
EVALUATION_QUESTIONS_PATH = (
    PROJECT_ROOT / "configs" / "evaluation_questions_candidate.json"
)
RETRIEVAL_GATE_POLICY_PATH = (
    PROJECT_ROOT / "configs" / "retrieval_gate_policy_candidate.json"
)
H2_FREEZE_PATH = PROJECT_ROOT / "configs" / "h2_freeze.json"
RETRIEVAL_GATE_PATH = PROJECT_ROOT / "configs" / "retrieval_gate.json"
CLASSIFICATION_PROMPT_PATH = PROJECT_ROOT / "prompts" / "classify_question.txt"
ANSWER_PROMPT_PATH = PROJECT_ROOT / "prompts" / "answer_question.txt"
JUDGE_PROMPT_PATH = PROJECT_ROOT / "prompts" / "judge_answer.txt"
EVALUATION_DIR_NAME = "evaluation"
JUDGE_INPUTS_DIR_NAME = "inputs_v1"
JUDGE_FORMAL_DIR_NAME = "formal"
RUNS_DIR = PROJECT_ROOT / "results" / "runs"
EXAMPLE_CANDIDATES_DIR = PROJECT_ROOT / "results" / "example_candidates"
CHECKPOINT_EXAMPLES_DIR = (
    PROJECT_ROOT / "results" / "checkpoints" / "examples"
)
