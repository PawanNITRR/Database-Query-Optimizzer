from flask import Flask, jsonify, render_template, request
from time import perf_counter
from privacy import Mask, select_only
from gnn import PlanGNN
from optimizer import optimize, ai_available
from database import connect, configure, explain, compare

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024
gnn = PlanGNN()


@app.before_request
def local_requests():
    if request.host.split(':')[0] not in {'127.0.0.1', 'localhost'}:
        return jsonify(error='Local access only.'), 403
    if request.method == 'POST' and not request.is_json:
        return jsonify(error='Use JSON requests.'), 415


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/api/status')
def status():
    try:
        with connect() as conn:
            conn.execute('SELECT 1')
        return jsonify(database=True, ai=ai_available())
    except Exception:
        return jsonify(database=False, ai=ai_available())


@app.post('/api/optimize')
def run():
    started = perf_counter()
    try:
        data = request.get_json()
        sql = data.get('query', '').strip()
        if not sql or len(sql) > 20000:
            raise ValueError('Enter a SELECT query (maximum 20,000 characters).')
        mask = Mask(sql)
        original = mask.tree.sql(dialect='postgres')
        with connect() as conn:
            configure(conn)
            graph = gnn.analyze(explain(conn, original)['Plan'])
            masked_candidate, reason, engine = optimize(mask.sql, graph, data.get('use_ai', True))
            candidate = mask.restore(masked_candidate)
            # Equality ignores ordering; retain the original when ORDER BY/LIMIT exist.
            from sqlglot import exp
            if any(isinstance(n, (exp.Order, exp.Limit, exp.Offset))
                   for tree in (mask.tree, select_only(candidate)) for n in tree.walk()):
                candidate = original
                masked_candidate = mask.sql
                reason = 'Kept the original query to preserve ordering and row limits.'
            metrics = compare(conn, original, candidate)
        return jsonify(masked_query=mask.sql, masked_optimized=masked_candidate,
                       optimized_query=candidate, explanation=reason, engine=engine,
                       graph=graph, metrics=metrics, changed=candidate != original,
                       total_ms=round((perf_counter() - started) * 1000, 1))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        # Database/parser messages can contain SQL or credentials; keep errors local and generic.
        return jsonify(error='Could not run the query. Check PostgreSQL, table/column names, and the 10-second query limit.'), 400


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
