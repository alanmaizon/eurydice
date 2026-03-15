import pytest


@pytest.fixture(autouse=True)
def _disable_remote_reference_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUTOR_REFERENCE_REMOTE_ENABLED", "false")
