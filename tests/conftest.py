import pytest
import app as app_module
from rl import RewriteAgent


@pytest.fixture(autouse=True)
def isolated_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'agent', RewriteAgent(tmp_path / 'policy.sqlite3'))
