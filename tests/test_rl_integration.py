import pytest
from app import app
from tests.test_demo import EXAMPLES


@pytest.mark.integration
def test_live_feedback_changes_next_action():
    client = app.test_client()
    first = client.post('/api/optimize', json={'query': EXAMPLES['products'], 'use_ai': False})
    assert first.status_code == 200, first.json
    assert first.json['rl']['action'] == 'inline'
    second = client.post('/api/optimize', json={'query': EXAMPLES['products'], 'use_ai': False})
    assert second.status_code == 200, second.json
    assert second.json['rl']['action'] == 'keep'
    assert second.json['rl']['reward'] == 0
    assert not second.json['changed']
