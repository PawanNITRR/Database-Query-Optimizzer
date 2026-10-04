import pytest
import app as app_module
from rl import RewriteAgent
from history import History


@pytest.fixture(autouse=True)
def isolated_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'agent', RewriteAgent(tmp_path / 'policy.sqlite3'))
    monkeypatch.setattr(app_module, 'history', History(tmp_path / 'history.sqlite3'))
    monkeypatch.setattr(app_module, 'proposals', {})
