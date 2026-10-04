import json
import pytest
import app
from workload_upload import parse_workload, match_statement
from workloads import REPORTS


def test_sql_parser_preserves_semicolons_inside_strings():
    records=parse_workload("SELECT 'a;b'; SELECT 2;", 'history.sql')
    assert len(records)==2 and "'a;b'" in records[0]['query']


@pytest.mark.parametrize('content,filename',[
    ('SELECT 1;', 'history.sql'),
    ('SELECT 1; DELETE FROM orders;', 'history.sql'),
    ('[]', 'history.json'),
    ('[{"query":"SELECT 1","duration_ms":-1},{"query":"SELECT 2"}]','history.json'),
    ('SELECT 1; SELECT 2;', 'history.txt'),
])
def test_invalid_batch_rejected(content,filename):
    with pytest.raises(ValueError):
        parse_workload(content,filename)


def test_upload_plan_is_scrubbed():
    records=parse_workload(json.dumps([{'query':'SELECT 1','plan':{'Node Type':'Seq Scan','Relation Name':'private','Filter':'secret'}},'SELECT 2']), 'history.json')
    assert 'private' not in str(records) and 'secret' not in str(records)


def test_live_multiple_queries_measured():
    response=app.app.test_client().post('/api/diagnose-file',json={
        'question':'Improve overall query performance','filename':'history.json','content':json.dumps([{'query':REPORTS['sales']},{'query':REPORTS['products']}]),'use_ai':False})
    assert response.status_code==200, response.json
    data=response.json
    assert data['query_count']==data['measured_queries']==2
    assert not data['failures']
    assert {i['query_number'] for i in data['improvements']}=={1,2}
    assert len([i for i in data['improvements'] if 'before_ms' in i])==2
    assert 'Structural sandbox gains are separate' in data['scope']


def test_statement_selects_sales_not_unrelated_reports():
    records=parse_workload(json.dumps(list(REPORTS.values())), 'history.json')
    selected, focus=match_statement(records,'Why is the sales reporting dashboard slow? Check its joins.')
    assert [i for i,_ in selected]==[1]
    assert focus=='sales + join'
    selected,_=match_statement(records,'Improve payment report performance')
    assert [i for i,_ in selected]==[3]


def test_no_match_does_not_analyze_every_query():
    records=parse_workload('SELECT id FROM product; SELECT id FROM customer;', 'history.sql')
    with pytest.raises(ValueError,match='No uploaded queries match'):
        match_statement(records,'Why are joins slow?')


def test_statement_required():
    response=app.app.test_client().post('/api/diagnose-file',json={'filename':'history.sql','content':'SELECT 1;SELECT 2;'})
    assert response.status_code==400
    assert 'what you want to diagnose' in response.json['error']
