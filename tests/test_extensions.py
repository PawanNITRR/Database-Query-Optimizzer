import json
import pytest
import app as module
from history import History, scrub_plan
from workloads import REPORTS
from simulation import simulate, sandbox_connect


def test_import_scrubs_all_sensitive_fields(tmp_path):
    h=History(tmp_path/'logs.sqlite3')
    h.add("SELECT private_salary FROM secret_staff WHERE email='private@example.com' -- secret", {'Plan': {'Node Type':'Seq Scan','Relation Name':'secret_staff','Filter':'private_salary > 9999','Plan Rows':100,'Total Cost':42}}, 125)
    text=json.dumps(h.list())
    for secret in ['private_salary','secret_staff','private@example.com','9999','Filter','Relation Name']:
        assert secret not in text
    assert h.list()[0]['plan']['Plan Rows']==100


def test_import_validation():
    client=module.app.test_client()
    assert client.post('/api/history',json={'records':[{'query':'DROP TABLE orders','plan':{}}]}).status_code==400
    assert client.get('/api/history').json['records']==[]
    with pytest.raises(ValueError):
        scrub_plan({'Node Type':'Seq Scan','Total Cost':float('nan')})


def test_history_evidence_is_structural(tmp_path):
    h=History(tmp_path/'logs.sqlite3')
    h.add('SELECT id FROM orders WHERE amount > 100', {'Node Type':'Seq Scan','Plan Rows':100}, 150)
    assert h.evidence('SELECT secret FROM staff WHERE salary > 12345')['structurally_similar_logs']==1
    assert h.evidence('SELECT secret FROM staff WHERE salary > 12345')['median_logged_duration_ms']==150


@pytest.mark.integration
def test_metadata_recommendations_and_approval():
    client=module.app.test_client()
    response=client.post('/api/advice',json={'query':'Why is the monthly sales dashboard slow?'})
    assert response.status_code==200,response.json
    data=response.json
    assert {r['kind'] for r in data['recommendations']} >= {'index','range','hash'}
    assert data['intent']=='sales'
    assert client.post('/api/approve',json={'token':data['token']}).status_code==400
    result=client.post('/api/simulate',json={'token':data['token']})
    assert result.status_code==200,result.json
    assert result.json['simulation']['source_tables_modified'] is False
    assert result.json['rl']['action_trials']==1
    approval=client.post('/api/approve',json={'token':data['token']})
    assert approval.json['approved'] and not approval.json['applied']


@pytest.mark.integration
@pytest.mark.parametrize('strategy',['index','range','hash'])
def test_synthetic_simulation_rolls_back_writes(strategy):
    with sandbox_connect() as conn:
        before=conn.execute('SELECT count(*) FROM baseline').fetchone()[0]
    result=simulate(strategy)
    assert result['baseline']['storage_bytes']>0
    assert result['proposed']['insert_ms_per_row']>=0
    if strategy=='index':
        assert result['hypothetical']['extension']=='HypoPG'
        assert result['hypothetical']['hypothetical_cost'] < result['hypothetical']['original_cost']
    with sandbox_connect() as conn:
        assert conn.execute('SELECT count(*) FROM baseline').fetchone()[0]==before==50000
        for table in ('indexed','partitioned','hashed'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==50000
