import os
from pathlib import Path

import pytest

CONFIG_PREFIXES = ("DISCORD_", "CHANNEL_", "ROLE_", "LLM_", "GEMINI_", "DATABASE_", "LOG_")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in os.environ:
        if key.startswith(CONFIG_PREFIXES):
            monkeypatch.delenv(key)
