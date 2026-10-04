"""Local masked history. Incoming raw log fields are scrubbed before persistence."""
import hashlib
import json
import math
import sqlite3
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
        conn.commit()
        return conn

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
