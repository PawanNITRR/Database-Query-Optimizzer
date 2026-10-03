import os
import statistics
import psycopg


def connect():
    return psycopg.connect(os.getenv('DATABASE_URL',
        'postgresql://querylab:querylab_local@127.0.0.1:55432/querylab'), connect_timeout=5)


def explain(conn, sql, analyze=False):
    options = 'ANALYZE, BUFFERS, ' if analyze else ''
    return conn.execute(f'EXPLAIN ({options}FORMAT JSON) ' + sql).fetchone()[0][0]


def configure(conn):
    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    conn.execute("SET LOCAL statement_timeout = '10s'")
    conn.execute("SET LOCAL lock_timeout = '2s'")


def compare(conn, original, candidate):
    # Multiset equality is checked inside PostgreSQL. No result rows go to AI.
    check = f'''SELECT EXISTS (
      (SELECT * FROM ({original}) a EXCEPT ALL SELECT * FROM ({candidate}) b)
      UNION ALL
      (SELECT * FROM ({candidate}) b EXCEPT ALL SELECT * FROM ({original}) a)
    )'''
    if conn.execute(check).fetchone()[0]:
        raise ValueError('Rewrite changed the result rows. It was rejected.')
    runs = {'original': [], 'optimized': []}
    # Warm both, then alternate execution order to reduce cache bias.
    explain(conn, original, True)
    explain(conn, candidate, True)
    last = {}
    for i in range(4):
        for label, sql in ([('original', original), ('optimized', candidate)] if i % 2 == 0
                           else [('optimized', candidate), ('original', original)]):
            last[label] = explain(conn, sql, True)
            runs[label].append(last[label]['Execution Time'])
    metrics = {}
    for label in runs:
        p = last[label]
        metrics[label] = {'execution_ms': statistics.median(runs[label]),
                          'planning_ms': p['Planning Time'], 'rows': p['Plan']['Actual Rows'],
                          'buffer_hits': p['Plan'].get('Shared Hit Blocks', 0),
                          'buffer_reads': p['Plan'].get('Shared Read Blocks', 0),
                          'runs_ms': runs[label]}
    old, new = metrics['original']['execution_ms'], metrics['optimized']['execution_ms']
    metrics['improvement_pct'] = round((old - new) / old * 100, 2) if old else 0
    return metrics
