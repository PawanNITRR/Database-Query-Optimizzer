import pytest
from privacy import Mask, select_only
from optimizer import local_rewrite
from gnn import PlanGNN
from app import app


def test_mask_roundtrip():
    sql = '''SELECT "Secret Column", amount FROM "Private Table"
             WHERE email = 'person@example.com' AND amount > 987654 -- private comment'''
    mask = Mask(sql)
    for value in ['Secret Column', 'Private Table', 'email', 'amount', 'person@example.com', '987654', 'private comment']:
        assert value not in mask.sql
    assert select_only(mask.restore(mask.sql)) == select_only(sql)


@pytest.mark.parametrize('sql', ['DELETE FROM orders', 'SELECT 1; SELECT 2',
    'WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x',
    'SELECT * INTO stolen FROM orders', "SELECT my_secret_function('x')"])
def test_reject_unsafe(sql):
    with pytest.raises(ValueError):
        Mask(sql)


def test_rewrite_and_unknown_names():
    mask = Mask("SELECT id FROM orders WHERE status IN ('completed', 'completed')")
    restored = mask.restore(local_rewrite(mask.sql))
    assert restored.count("'completed'") == 1
    with pytest.raises(ValueError):
        mask.restore('SELECT secret FROM stolen')
    with pytest.raises(ValueError):
        mask.restore('SELECT 12345')


def test_external_parameter_rejected():
    with pytest.raises(ValueError):
        Mask('SELECT :private_parameter')


def test_ai_payload_is_masked(monkeypatch):
    import json
    import optimizer
    mask = Mask("SELECT confidential_salary FROM private_employees WHERE email = 'secret@example.com'")
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({'response': json.dumps({'sql': mask.sql, 'explanation': 'No safe rewrite.'})}).encode()
    def fake_model(request, timeout):
        payload = request.data.decode()
        for private in ['confidential_salary', 'private_employees', 'email', 'secret@example.com']:
            assert private not in payload
        assert 'id_' in payload and 'value_0' in payload
        return Response()
    monkeypatch.setattr(optimizer.urllib.request, 'urlopen', fake_model)
    result, reason, engine = optimizer.optimize(mask.sql, [], True)
    assert mask.restore(result) == mask.tree.sql(dialect='postgres')
    assert engine == 'Ollama + prototype GNN'


def test_graph_does_not_expose_plan_text():
    plan = {'Node Type': 'Seq Scan', 'Relation Name': 'secret_table', 'Filter': "private = 'abc'",
            'Plan Rows': 100, 'Total Cost': 42, 'Plans': [{'Node Type': 'Sort', 'Total Cost': 10}]}
    result = PlanGNN().analyze(plan)
    assert len(result) == 2
    assert 'secret' not in str(result) and 'abc' not in str(result)
    assert all(0 <= n['score'] <= 1 for n in result)


def test_api_validation():
    client = app.test_client()
    assert client.get('/').status_code == 200
    assert client.post('/api/optimize', json={'query': 'DROP TABLE orders'}).status_code == 400
    assert client.post('/api/optimize', data='query=SELECT 1').status_code == 415


@pytest.mark.integration
def test_postgres_pipeline():
    client = app.test_client()
    response = client.post('/api/optimize', json={'query': "SELECT id FROM orders WHERE status IN ('completed', 'completed')", 'use_ai': False})
    assert response.status_code == 200, response.json
    data = response.json
    assert data['changed']
    assert data['metrics']['original']['rows'] == data['metrics']['optimized']['rows'] == 50000
    assert len(data['metrics']['original']['runs_ms']) == 4
    assert 'orders' not in data['masked_query']


@pytest.mark.integration
def test_retail_join_pipeline():
    query = '''SELECT o.id, c.name AS customer, p.name AS product, o.amount, t.payment_method
        FROM orders o JOIN customer c ON c.id = o.customer_id
        JOIN product p ON p.id = o.product_id
        JOIN "transaction" t ON t.order_id = o.id
        WHERE o.status IN ('completed', 'completed')'''
    response = app.test_client().post('/api/optimize', json={'query': query, 'use_ai': False})
    assert response.status_code == 200, response.json
    assert response.json['metrics']['optimized']['rows'] == 50000
    assert response.json['changed']
