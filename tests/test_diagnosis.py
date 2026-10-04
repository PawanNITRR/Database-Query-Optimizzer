from workloads import query_from_input
from diagnosis import plan_facts
import app
import diagnosis


def test_weekly_report_is_seven_days():
    for topic in ('sales', 'products', 'payments'):
        sql, intent = query_from_input('Why is weekly ' + topic + ' slow?')
        assert intent == 'weekly_' + topic
        assert '2025-06-23' in sql and '2025-06-30' in sql


def test_facts_do_not_invent_nested_join_or_timeout():
    text = plan_facts([dict(operator='Index Scan', rows=12)])
    assert '0 sequential scans' in text and '0 nested-loop' in text
    assert 'not proof' in text


def test_live_diagnosis_history_precedes_current_run():
    client = app.app.test_client()
    response = client.post('/api/diagnose', json={'question':'Why is weekly sales slow?', 'use_ai':False})
    assert response.status_code == 200, response.json
    data = response.json
    assert data['historical_evidence']['structurally_similar_logs'] == 0
    assert data['simulation'] is not None
    assert data['result']['changed']
    assert '2025-06-23' in data['report_query']
    assert 'orders' not in data['result']['masked_query']
    assert 'cannot be added' in ' '.join(data['answer'])
    again = client.post('/api/diagnose', json={'question':'Why is weekly sales slow?', 'use_ai':False}).json
    summaries = again['historical_evidence']['recent_plan_summaries']
    assert len(summaries) == 1
    assert 'Seq Scan' in summaries[0]['operators']


def test_associated_sql_and_unavailable_sandbox(monkeypatch):
    def unavailable(action):
        raise RuntimeError('private connection details')
    monkeypatch.setattr(diagnosis, 'simulate', unavailable)
    response = app.app.test_client().post('/api/diagnose', json={
        'question':'Why is this slow?', 'query':'SELECT id FROM product WHERE id = 1', 'use_ai':False})
    assert response.status_code == 200
    assert response.json['intent'] is None
    assert response.json['simulation'] is None
    assert 'private connection' not in str(response.json)


def test_unknown_question_is_not_arbitrary_sql_generation():
    response = app.app.test_client().post('/api/diagnose', json={'question':'Explain the weather'})
    assert response.status_code == 400
