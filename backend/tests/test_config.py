from app.core.config import Settings


def test_log_json_defaults_on_for_vercel(monkeypatch):
    monkeypatch.delenv("LOG_JSON", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert Settings().log_json is True

    monkeypatch.delenv("VERCEL")
    assert Settings().log_json is False


def test_log_json_can_be_overridden(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("LOG_JSON", "false")
    assert Settings().log_json is False
