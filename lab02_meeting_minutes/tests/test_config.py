from lab02_meeting_minutes.src.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_settings


def test_default_model_is_deepseek_v4_flash(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    settings = load_settings()
    assert settings.model == DEFAULT_MODEL == "deepseek-v4-flash"
    assert settings.base_url == DEFAULT_BASE_URL
