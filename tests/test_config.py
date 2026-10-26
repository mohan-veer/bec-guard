from app.config import load_settings


def test_no_keys_means_mock(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("MOCK_MODE", "false")
    s = load_settings()
    assert s.llm_mock and s.tavily_mock


def test_mock_mode_flag_overrides_keys(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "k1")
    monkeypatch.setenv("TAVILY_API_KEY", "k2")
    monkeypatch.setenv("MOCK_MODE", "true")
    s = load_settings()
    assert s.llm_mock and s.tavily_mock


def test_keys_and_flag_off_means_real(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "k1")
    monkeypatch.setenv("TAVILY_API_KEY", "k2")
    monkeypatch.setenv("MOCK_MODE", "false")
    s = load_settings()
    assert not s.llm_mock and not s.tavily_mock


def test_each_service_decides_mock_on_its_own_key(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "k1")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("MOCK_MODE", "false")
    s = load_settings()
    assert not s.llm_mock and s.tavily_mock


def test_model_ids_come_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_NANO", "some/nano")
    assert load_settings().model_nano == "some/nano"
