"""Validate uploaded multi-query workloads and measure each query locally."""
import json
import math
import re
import sqlglot
from privacy import Mask
from history import scrub_plan
from database import connect, configure, explain
from recommendations import recommend
from simulation import simulate
from rl import LABELS


def match_statement(records, question):
    """Bounded local matching: report topic, identifiers, and SQL operations."""
    from sqlglot import exp
    lower = question.lower()
    words = set(re.findall(r'[a-z_]+', lower))
    topic = None
    if words & {'payment','payments','paid','transaction','transactions'}:
        topic = 'payments'
    elif words & {'sales','revenue'}:
        topic = 'sales'
    elif words & {'product','products','category','categories','units'}:
        topic = 'products'
    elif words & {'customer','customers'}:
        topic = 'customer'
    focus = 'join' if words & {'join','joins','joining'} else 'sort' if words & {'sort','sorting','order'} else 'aggregation' if words & {'aggregate','aggregation','grouping','group'} else None
    known_tables = set()
    trees = []
    for r in records:
        tree=sqlglot.parse_one(r['query'],read='postgres');trees.append(tree)
        known_tables.update(t.name.lower() for t in tree.find_all(exp.Table))
    named_tables = words & known_tables
    selected=[]
    for i,(r,tree) in enumerate(zip(records,trees),1):
        tables={t.name.lower() for t in tree.find_all(exp.Table)}
        is_sales={'customer','product','orders'} <= tables
        relevant = (topic is None or topic=='sales' and is_sales or topic=='products' and {'orders','product'}<=tables and not is_sales or topic=='payments' and 'transaction' in tables and not is_sales or topic=='customer' and 'customer' in tables)
        if named_tables and not named_tables <= tables:
            relevant=False
        operation = {'join':exp.Join,'sort':exp.Order,'aggregation':exp.Group}.get(focus)
        if operation and not any(tree.find_all(operation)):
            relevant=False
        if relevant:
            selected.append((i,r))
    if not topic and not focus and not named_tables and not words & {'slow','slower','performance','optimize','optimise','optimization','improvements','improve','timeout','timeouts','timing','latency','queries','query','index','indexes','partition','partitioning'}:
        raise ValueError('Describe a query-performance issue, report topic, table, joins, sorting or aggregation.')
    if not selected:
        raise ValueError('No uploaded queries match that statement. Include relevant historical queries or adjust the report/table/operation you want to diagnose.')
    description = ' + '.join(filter(None,[topic,', '.join(sorted(named_tables)),focus])) or 'overall query performance'
    return selected, description


def parse_workload(content, filename):
    if not isinstance(content, str) or len(content.encode()) > 200000:
        raise ValueError('Upload a SQL or JSON file smaller than 200 KB.')
    if filename.lower().endswith('.json'):
        try:
            records = json.loads(content)
        except Exception:
            raise ValueError('Invalid JSON. Use an array of SQL strings or objects with query, optional plan and duration_ms.')
    elif filename.lower().endswith('.sql'):
        try:
            records = [t.sql(dialect='postgres') for t in sqlglot.parse(content, read='postgres') if t is not None]
        except Exception:
            raise ValueError('Invalid SQL file. Separate SELECT queries with semicolons.')
    else:
        raise ValueError('Choose a .sql or .json file.')
    if not isinstance(records, list) or not 2 <= len(records) <= 10:
        raise ValueError('Include 2–10 historical SELECT queries in the file.')
    clean = []
    for i, record in enumerate(records, 1):
        if isinstance(record, str):
            record = {'query': record}
        if not isinstance(record, dict) or not isinstance(record.get('query'), str) or len(record['query']) > 20000:
            raise ValueError('Query %d needs SELECT SQL, at most 20,000 characters.' % i)
        try:
            mask = Mask(record['query'])
            plan = scrub_plan(record['plan']) if 'plan' in record else None
            duration = record.get('duration_ms')
            if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration < 0):
                raise ValueError()
        except Exception:
            raise ValueError('Query %d is invalid. Use read-only SELECT SQL and finite nonnegative historical metrics.' % i)
        clean.append(dict(query=mask.tree.sql(dialect='postgres'), plan=plan, duration_ms=duration))
    return clean


def analyze_workload(data, gnn, optimize_query):
    records = parse_workload(data.get('content'), data.get('filename', ''))
    question = data.get('question', '').strip()
    if not question or len(question) > 2000:
        raise ValueError('Enter what you want to diagnose (maximum 2,000 characters).')
    selected, focus = match_statement(records, question)
    improvements, failures, simulations = [], [], {}
    total_before, total_after, measured = 0, 0, 0
    for i, record in selected:
        try:
            # Uploaded logs are untrusted evidence; fresh measurements establish gains.
            with connect() as conn:
                configure(conn)
                current = explain(conn, record['query'])['Plan']
                recs = recommend(conn, record['query'])
            graph = gnn.analyze(record['plan'] or current)
            result = optimize_query({'query':record['query'], 'use_ai':bool(data.get('use_ai', False))})
            m=result['metrics'];measured+=1
            total_before+=m['original']['execution_ms'];total_after+=m['optimized']['execution_ms']
            evidence = 'Uploaded execution plan' if record['plan'] else 'Fresh EXPLAIN plan (the file contains SQL only)'
            top=gnn.explain(graph)[0]['reason'] if graph else ''
            improvements.append(dict(query_number=i, title='Query %d · %s' % (i, 'SQL rewrite' if result['changed'] else 'Keep current SQL'),
                improvement_pct=m['improvement_pct'] if result['changed'] else None,
                detail=result['explanation'], evidence=evidence + ': ' + top,
                before_ms=m['original']['execution_ms'], after_ms=m['optimized']['execution_ms'],
                historical_duration_ms=record['duration_ms'], original_sql=record['query'], optimized_sql=result['optimized_query'],
                scope='Fresh local PostgreSQL measurement; equivalent result rows verified. Uploaded historical durations are context, not the speedup baseline.'))
            for rec in recs:
                if rec.get('already_present'):
                    continue
                kind=rec['kind']
                if kind not in simulations:
                    try:
                        simulations[kind]=simulate(kind)
                    except Exception:
                        simulations[kind]=None
                s=simulations[kind]
                improvements.append(dict(query_number=i, title='Query %d · %s · %s' % (i,LABELS[kind],rec['table']),
                    improvement_pct=s['read_improvement_pct'] if s else None,
                    detail=rec['reason'], scope=s['scope'] if s else 'Sandbox unavailable; improvement not measured.',
                    ddl=rec['ddl']))
        except Exception:
            failures.append(dict(query_number=i, error='Could not benchmark this query. Check its tables, syntax and runtime limit; no source tables were changed.'))
    return dict(improvements=improvements, failures=failures, query_count=len(records), matched_queries=len(selected),
                selected_query_numbers=[i for i,_ in selected], focus=focus, measured_queries=measured,
                combined_improvement_pct=round((total_before-total_after)/total_before*100,2) if total_before else None,
                scope='Combined percentage uses the sum of fresh original and selected SQL runtimes for successful queries only. Structural sandbox gains are separate and never added.',
                question=question)
