import json
import re
from pathlib import Path
import pytest
from app import app
from privacy import Mask
from optimizer import local_rewrite

EXAMPLES = dict(re.findall(r'(sales|products|payments): `([^`]+)`',
    (Path(__file__).resolve().parents[1] / 'static/examples.js').read_text()))


@pytest.mark.parametrize('query', EXAMPLES.values())
def test_masked_cte_rewrite(query):
    mask = Mask(query)
    candidate = mask.restore(local_rewrite(mask.sql))
    assert 'NOT MATERIALIZED' in candidate
    assert '2025' not in mask.sql


def test_complex_cte_is_not_inlined():
    query = 'WITH x AS MATERIALIZED (SELECT DISTINCT customer_id FROM orders) SELECT * FROM x'
    assert 'NOT MATERIALIZED' not in local_rewrite(query)
    query = 'WITH x AS MATERIALIZED (SELECT * FROM orders) SELECT * FROM x a JOIN x b ON a.id = b.id'
    assert 'NOT MATERIALIZED' not in local_rewrite(query)


@pytest.mark.integration
@pytest.mark.parametrize('name,query', EXAMPLES.items())
def test_demo_reports(name, query):
    response = app.test_client().post('/api/optimize', json={'query': query, 'use_ai': False})
    assert response.status_code == 200, response.json
    data = response.json
    assert data['changed']
    assert data['rl']['action'] == 'inline'
    assert data['rl']['action_trials'] == 1
    assert data['metrics']['original']['rows'] == data['metrics']['optimized']['rows'] > 0
    print(json.dumps({'report': name, 'response_ms': data['total_ms'],
        'original_ms': data['metrics']['original']['execution_ms'],
        'optimized_ms': data['metrics']['optimized']['execution_ms'],
        'improvement_pct': data['metrics']['improvement_pct']}))


@pytest.mark.integration
def test_demo_data_integrity():
    from database import connect
    with connect() as conn:
        assert conn.execute('SELECT (SELECT count(*) FROM customer), (SELECT count(*) FROM product), (SELECT count(*) FROM orders), (SELECT count(*) FROM "transaction")').fetchone() == (10000, 5000, 200000, 200000)
        assert conn.execute('SELECT count(*) FROM orders o JOIN "transaction" t ON t.order_id=o.id WHERE t.amount <> o.amount OR t.transaction_date <> o.order_date').fetchone()[0] == 0
        assert conn.execute('SELECT count(DISTINCT payment_method) FROM "transaction" WHERE status=\'paid\'').fetchone()[0] == 4
        assert conn.execute('SELECT count(DISTINCT quantity), count(DISTINCT order_date) FROM orders').fetchone() == (5, 730)
