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
    sql, _ = query_from_input('weekly sales')
    assert client.post('/api/optimize', json={'query':sql,'use_ai':False}).status_code == 200
    response = client.post('/api/diagnose', json={'question':'Why is weekly sales slow?', 'use_ai':False})
    assert response.status_code == 200, response.json
    data = response.json
    assert data['historical_evidence']['structurally_similar_logs'] == 1
    assert data['simulation'] is not None
    assert data['improvements']
    assert '2025-06-23' in data['report_query']
    assert 'orders' not in data['result']['masked_query']
    assert 'cannot be added' in ' '.join(data['answer'])
    again = client.post('/api/diagnose', json={'question':'Why is weekly sales slow?', 'use_ai':False}).json
    summaries = again['historical_evidence']['recent_plan_summaries']
    assert len(summaries) == 2
    assert summaries[0]['plan']


def test_associated_sql_and_unavailable_sandbox(monkeypatch):
    def unavailable(action):
        raise RuntimeError('private connection details')
    monkeypatch.setattr(diagnosis, 'simulate', unavailable)
    client = app.app.test_client()
    client.post('/api/optimize', json={'query':'SELECT id FROM product WHERE id = 1','use_ai':False})
    response = client.post('/api/diagnose', json={
        'question':'Why is this slow?', 'query':'SELECT id FROM product WHERE id = 1', 'use_ai':False})
    assert response.status_code == 200
    assert response.json['intent'] == 'historical_execution'
    assert response.json['simulation'] is None
    assert 'private connection' not in str(response.json)


def test_unknown_question_is_not_arbitrary_sql_generation():
    response = app.app.test_client().post('/api/diagnose', json={'question':'Explain the weather'})
    assert response.status_code == 400


def test_no_history_does_not_invent_a_report():
    response = app.app.test_client().post('/api/diagnose', json={'question':'Why is sales slow?'})
    assert response.status_code == 400
    assert 'past executions' in response.json['error']


def test_history_replay_is_encrypted_and_database_scoped(tmp_path, monkeypatch):
    from history import History
    h=History(tmp_path/'local.sqlite3')
    query="SELECT id FROM product WHERE id = 42"
    h.add_execution(query, {'Node Type':'Seq Scan','Plan Rows':5}, 10)
    assert query.encode() not in h.path.read_bytes()
    selected, evidence=h.workload('Why are queries slow?')
    assert selected == query
    assert evidence['selected_record_id'] == 1
    monkeypatch.setenv('DATABASE_URL','postgresql://different-test-database')
    import pytest
    with pytest.raises(ValueError, match='past executions'):
        h.workload('Why are queries slow?')
