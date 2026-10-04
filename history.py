"""Local masked history. Incoming raw log fields are scrubbed before persistence."""
import hashlib
import json
import math
import sqlite3
import os
from pathlib import Path
from contextlib import closing
from privacy import Mask


def number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError('Plan statistics must be finite nonnegative numbers.')
    return value


def scrub_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError('Execution plan must be a JSON object.')
    from gnn import OPERATORS
    def visit(node, depth=0):
        if depth > 40:
            raise ValueError('Execution plan is too deeply nested.')
        clean = {'Node Type': node.get('Node Type') if node.get('Node Type') in OPERATORS else 'Other'}
        for key in ('Total Cost', 'Plan Rows', 'Actual Total Time', 'Actual Rows', 'Actual Loops'):
            if key in node:
                clean[key] = number(node[key])
        children = node.get('Plans', [])
        if not isinstance(children, list) or len(children) > 100:
            raise ValueError('Invalid execution plan children.')
        clean['Plans'] = [visit(child, depth + 1) for child in children]
        return clean
    return visit(plan.get('Plan', plan))


class History:
    def __init__(self, path=None):
        self.path = Path(path or Path(__file__).parent / 'data/history.sqlite3')

    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, fingerprint TEXT, masked_sql TEXT, plan TEXT, duration REAL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
        conn.execute('CREATE TABLE IF NOT EXISTS executions (log_id INTEGER PRIMARY KEY, scope TEXT, topic TEXT, query_hash TEXT, encrypted_sql BLOB)')
        conn.commit()
        return conn

    def cipher(self):
        from cryptography.fernet import Fernet
        key_path = self.path.with_suffix('.key')
        try:
            with key_path.open('xb') as handle:
                handle.write(Fernet.generate_key())
        except FileExistsError:
            pass
        return Fernet(key_path.read_bytes())

    def scope(self):
        # Never put connection credentials in the history record.
        return hashlib.sha256(os.getenv('DATABASE_URL', 'local-demo-55432-querylab').encode()).hexdigest()

    def add_execution(self, query, plan, duration):
        """Only actually benchmarked queries can be replayed by diagnosis."""
        from sqlglot import exp
        tree = Mask(query).tree
        tables = {t.name.lower() for t in tree.find_all(exp.Table)}
        topic = 'sales' if {'customer', 'product', 'orders'} <= tables else 'products' if {'product', 'orders'} <= tables else 'payments' if 'transaction' in tables else 'other'
        canonical = tree.sql(dialect='postgres')
        encrypted = self.cipher().encrypt(canonical.encode())
        log_id = self.add(query, plan, duration)
        with closing(self.db()) as conn, conn:
            conn.execute('INSERT INTO executions VALUES (?,?,?,?,?)', (log_id, self.scope(), topic,
                         hashlib.sha256(canonical.encode()).hexdigest(), encrypted))
        return log_id

    def workload(self, question, associated=''):
        """Resolve locally to actual prior executions, never generate a new report."""
        from workloads import query_from_input
        from statistics import median
        query_hash = None
        if associated:
            canonical = Mask(associated).tree.sql(dialect='postgres')
            query_hash = hashlib.sha256(canonical.encode()).hexdigest()
            topic = None
        else:
            try:
                _, topic = query_from_input(question)
                if topic is None:
                    raise ValueError()
                topic = topic.removeprefix('weekly_')
            except ValueError:
                topic = None
                if not any(w in question.lower() for w in ('slow', 'performance', 'optimiz', 'query', 'queries', 'timeout', 'timing out')):
                    raise ValueError('Ask about query performance, sales, products or payments.')
        with closing(self.db()) as conn:
            rows = conn.execute('SELECT e.log_id,e.topic,e.query_hash,e.encrypted_sql,l.plan,l.duration,l.created FROM executions e JOIN logs l ON l.id=e.log_id WHERE e.scope=? ORDER BY e.log_id DESC LIMIT 100', (self.scope(),)).fetchall()
        rows = [r for r in rows if (r[2] == query_hash if query_hash else topic is None or r[1] == topic)]
        if not rows:
            raise ValueError('No relevant past executions found for this database. Run the report with Optimize & compare first, then diagnose it. Imported unverified plans are not replayed.')
        # Prefer a historical weekly workload for a weekly question; do not alter dates.
        if 'week' in question.lower() and not associated:
            weekly = []
            import re
            from datetime import date
            for r in rows:
                dates = re.findall(r"'(\d{4}-\d{2}-\d{2})'", self.cipher().decrypt(r[3]).decode())
                if len(dates) >= 2 and abs((date.fromisoformat(dates[1])-date.fromisoformat(dates[0])).days) == 7:
                    weekly.append(r)
            if weekly:
                rows = weekly
        selected = max(rows, key=lambda r: r[5])
        same = [r for r in rows if r[2] == selected[2]]
        query = self.cipher().decrypt(selected[3]).decode()
        return query, dict(selected_record_id=selected[0], matched_executions=len(rows),
            structurally_similar_logs=len(same), median_logged_duration_ms=median(r[5] for r in same),
            scope='Actual benchmark history for this database; grouped by exact local SQL hash. Slowest matching execution selected. Report-topic matching is limited to the demo tables.',
            recent_plan_summaries=[dict(record_id=r[0], created_at=r[6], duration_ms=r[5], plan=json.loads(r[4])) for r in same[:5]])

    def add(self, query, plan, duration=0):
        mask = Mask(query)
        clean = scrub_plan(plan)
        # Fingerprint is structural and excludes actual identifier/literal contents.
        shape = '|'.join(type(n).__name__ for n in mask.tree.walk())
        fingerprint = hashlib.sha256(shape.encode()).hexdigest()
        with closing(self.db()) as conn, conn:
            cursor = conn.execute('INSERT INTO logs(fingerprint,masked_sql,plan,duration) VALUES (?,?,?,?)',
                (fingerprint, mask.sql, json.dumps(clean), number(duration)))
            return cursor.lastrowid

    def list(self):
        with closing(self.db()) as conn:
            rows = conn.execute('SELECT id,fingerprint,masked_sql,plan,duration,created FROM logs ORDER BY id DESC LIMIT 50').fetchall()
        return [dict(id=i, fingerprint=f, masked_query=s, plan=json.loads(p), duration_ms=d, created_at=c)
                for i, f, s, p, d, c in rows]

    def evidence(self, query):
        from statistics import median
        tree=Mask(query).tree
        fingerprint=hashlib.sha256('|'.join(type(n).__name__ for n in tree.walk()).encode()).hexdigest()
        matches=[r for r in self.list() if r['fingerprint']==fingerprint]
        def operators(node):
            return [node['Node Type']] + [op for child in node.get('Plans', []) for op in operators(child)]
        recent_plans = [dict(record_id=r['id'], created_at=r['created_at'],
                            operators=operators(r['plan']), duration_ms=r['duration_ms']) for r in matches[:5]]
        return {'structurally_similar_logs':len(matches),
                'recent_plan_summaries':recent_plans,
                'median_logged_duration_ms':median(r['duration_ms'] for r in matches) if matches else None,
                'scope':'Structure similarity only; identifiers and values are not used to link history.'}
