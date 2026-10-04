"""HypoPG and real synthetic-table benchmarks in a separate PostgreSQL server."""
import statistics
import threading
import psycopg
from psycopg import sql
from database import explain

LOCK = threading.Lock()


def sandbox_connect():
    # Deliberately not configurable to DATABASE_URL: no source writes are possible.
    return psycopg.connect('postgresql://simulator:simulator_local@127.0.0.1:55433/simulation', connect_timeout=3)


def sizes(conn, table):
    return conn.execute('SELECT coalesce(sum(pg_total_relation_size(relid)),0)::bigint FROM pg_partition_tree(%s::regclass) WHERE isleaf', (table,)).fetchone()[0] or conn.execute('SELECT pg_total_relation_size(%s::regclass)', (table,)).fetchone()[0]


def benchmark(conn, table, mode):
    where = "customer_id = 100" if mode == 'hash' else "status='completed' AND order_date >= DATE '2025-06-01' AND order_date < DATE '2025-07-01'"
    query = sql.SQL('SELECT count(*) FROM {} WHERE ' + where).format(sql.Identifier(table)).as_string(conn)
    reads, writes = [], []
    storage = sizes(conn, table)
    for i in range(4):
        reads.append(explain(conn, query, True)['Execution Time'])
        conn.execute('SAVEPOINT write_probe')
        statement = sql.SQL("INSERT INTO {} SELECT n, (n*7919)%10000, 'completed', DATE '2025-06-15', 100 FROM generate_series(50001,50500) n").format(sql.Identifier(table)).as_string(conn)
        writes.append(explain(conn, statement, True)['Execution Time'] / 500)
        conn.execute('ROLLBACK TO SAVEPOINT write_probe')
        conn.execute('RELEASE SAVEPOINT write_probe')
    return dict(read_ms=statistics.median(reads), insert_ms_per_row=statistics.median(writes), storage_bytes=storage, read_samples_ms=reads, write_samples_ms_per_row=writes)


def simulate(action):
    target = {'index': 'indexed', 'range': 'partitioned', 'hash': 'hashed', 'structure_keep': 'baseline'}[action]
    with LOCK, sandbox_connect() as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        base = benchmark(conn, 'baseline', action)
        hypothetical = None
        if action == 'index':
            before = explain(conn, "SELECT count(*) FROM baseline WHERE status='completed' AND order_date>=DATE '2025-06-01' AND order_date<DATE '2025-07-01'")['Plan']['Total Cost']
            oid = conn.execute("SELECT indexrelid FROM hypopg_create_index('CREATE INDEX ON baseline(status,order_date)')").fetchone()[0]
            after = explain(conn, "SELECT count(*) FROM baseline WHERE status='completed' AND order_date>=DATE '2025-06-01' AND order_date<DATE '2025-07-01'")['Plan']['Total Cost']
            estimated_bytes = conn.execute('SELECT hypopg_relation_size(%s::oid)', (oid,)).fetchone()[0]
            actual_bytes = conn.execute("SELECT sum(pg_relation_size(indexrelid))::bigint FROM pg_index WHERE indrelid='indexed'::regclass").fetchone()[0]
            hypothetical = dict(extension='HypoPG', original_cost=before, hypothetical_cost=after,
                estimated_index_bytes=estimated_bytes, physical_index_bytes=actual_bytes,
                storage_estimate_error_pct=round(abs(estimated_bytes-actual_bytes)/max(actual_bytes,1)*100,2))
            conn.execute('SELECT hypopg_reset()')
        variant = benchmark(conn, target, action)
        # Transaction is rolled back even after successful measurements.
        conn.rollback()
    gain = (base['read_ms'] - variant['read_ms']) / max(base['read_ms'], .001) if target != 'baseline' else 0
    write_delta = variant['insert_ms_per_row'] - base['insert_ms_per_row']
    storage_delta = variant['storage_bytes'] - base['storage_bytes']
    penalty = .2 * max(0, write_delta / max(base['insert_ms_per_row'], .001)) + .02 * max(0, storage_delta / max(base['storage_bytes'], 1))
    return dict(action=action, baseline=base, proposed=variant, read_improvement_pct=round(gain*100,2),
                write_latency_delta_ms_per_row=round(write_delta,6), storage_delta_bytes=storage_delta,
                reward=max(-1, min(1, gain - penalty)), hypothetical=hypothetical,
                scope='Synthetic 50,000-row scenario in a separate database; not an exact prediction for the source workload.',
                source_tables_modified=False, distributed_network_simulated=False)
