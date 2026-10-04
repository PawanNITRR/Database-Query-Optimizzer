"""Recommendations from query structure and catalog metadata, never table rows."""
from collections import defaultdict
from psycopg import sql
from sqlglot import exp
from privacy import select_only
from datetime import date


def recommend(conn, query):
    tree = select_only(query)
    physical = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)
                if isinstance(t.this, exp.Identifier) and not t.db and not t.catalog}
    for cte in tree.find_all(exp.CTE):
        tables = list(cte.this.find_all(exp.Table))
        if len(tables) == 1:
            for alias, name in list(physical.items()):
                if name == cte.alias:
                    physical[alias] = tables[0].name
    catalog = {}
    for table in set(physical.values()):
        rows = conn.execute('SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=%s', (table,)).fetchall()
        if rows:
            catalog[table] = dict(rows)
    equality, ranges, joins = defaultdict(list), defaultdict(list), defaultdict(list)
    def resolve(col):
        table = physical.get(col.table)
        if not col.table:
            matches = [t for t, columns in catalog.items() if col.name in columns]
            table = matches[0] if len(matches) == 1 else None
        return table if table in catalog and col.name in catalog[table] else None
    for predicate in tree.walk():
        if isinstance(predicate, (exp.EQ, exp.In, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)):
            for col in predicate.find_all(exp.Column):
                table = resolve(col)
                if table:
                    is_join = isinstance(predicate, exp.EQ) and isinstance(predicate.this, exp.Column) and isinstance(predicate.expression, exp.Column)
                    target = joins if is_join else equality if isinstance(predicate, (exp.EQ, exp.In)) else ranges
                    if col.name not in target[table]:
                        target[table].append(col.name)
    proposals = []
    for table in catalog:
        columns = (equality[table] + [c for c in ranges[table] if c not in equality[table]])[:3] or joins[table][:3]
        if columns:
            ddl = sql.SQL('CREATE INDEX ON public.{} ({})').format(sql.Identifier(table),
                    sql.SQL(', ').join(map(sql.Identifier, columns))).as_string(conn)
            existing = conn.execute('SELECT indexdef FROM pg_indexes WHERE schemaname=\'public\' AND tablename=%s', (table,)).fetchall()
            def key(text):
                return text.split(' USING ')[-1].replace('"', '').strip()
            signature = 'btree (' + ', '.join(columns) + ')'
            present = any(key(row[0]).startswith(signature) for row in existing)
            proposals.append({'kind': 'index', 'table': table, 'columns': columns, 'ddl': ddl,
                'already_present': present, 'reason': 'Equality/join columns precede range columns in a candidate B-tree index. Existing indexes and planner costs must be checked; optimality is not guaranteed.'})
        dates = [c for c in ranges[table] if catalog[table][c] in {'date', 'timestamp without time zone', 'timestamp with time zone'}]
        if dates:
            col = dates[0]
            ddl = sql.SQL('CREATE TABLE {} (LIKE public.{}) PARTITION BY RANGE ({});').format(
                sql.Identifier(table + '_proposed'), sql.Identifier(table), sql.Identifier(col)).as_string(conn)
            dates_in_query=[]
            for literal in tree.find_all(exp.Literal):
                try:
                    dates_in_query.append(date.fromisoformat(literal.this))
                except (ValueError, TypeError):
                    pass
            start=min(dates_in_query) if dates_in_query else date(2025,1,1)
            start=start.replace(day=1)
            end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
            ddl += '\n' + sql.SQL('CREATE TABLE {} PARTITION OF {} FOR VALUES FROM ({}) TO ({});').format(
                sql.Identifier(table + '_proposed_month'),sql.Identifier(table + '_proposed'),sql.Literal(start),sql.Literal(end)).as_string(conn)
            ddl += '\n' + sql.SQL('CREATE TABLE {} PARTITION OF {} DEFAULT;').format(
                sql.Identifier(table + '_proposed_default'),sql.Identifier(table + '_proposed')).as_string(conn)
            proposals.append({'kind': 'range', 'table': table, 'columns': [col], 'ddl': ddl,
                'reason': 'Date-range access suggests monthly partitions with pruning. Bounds, retention policy, keys and migration require review.'})
        join_keys = [c for c in joins[table] if c.endswith('_id')]
        if join_keys:
            col = join_keys[0]
            ddl = sql.SQL('CREATE TABLE {} (LIKE public.{}) PARTITION BY HASH ({});').format(
                sql.Identifier(table + '_hash_proposed'), sql.Identifier(table), sql.Identifier(col)).as_string(conn)
            for bucket in range(4):
                ddl += '\n' + sql.SQL('CREATE TABLE {} PARTITION OF {} FOR VALUES WITH (MODULUS 4, REMAINDER {});').format(
                    sql.Identifier(table + '_hash_' + str(bucket)), sql.Identifier(table + '_hash_proposed'),sql.Literal(bucket)).as_string(conn)
            proposals.append({'kind': 'hash', 'table': table, 'columns': [col], 'ddl': ddl,
                'reason': 'Hash distribution by a frequently used key is a sharding candidate. Local hash partitions test routing only; distributed sharding also requires colocated joins and a topology/network benchmark.'})
    return proposals
