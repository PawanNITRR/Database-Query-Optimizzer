from flask import Flask, jsonify, render_template, request
from time import perf_counter
from privacy import Mask, select_only
from gnn import PlanGNN
from optimizer import optimize, ai_available, local_rewrite
from rl import RewriteAgent, context, runtime_reward, LABELS
from history import History, scrub_plan
from recommendations import recommend
from simulation import simulate
from workloads import query_from_input
import uuid
import os
from database import connect, configure, explain, compare

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024
gnn = PlanGNN()
agent = RewriteAgent()
history = History()
proposals = {}


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


def optimize_query(data):
    started = perf_counter()
    sql = data.get('query', '').strip()
    if not sql or len(sql) > 20000:
        raise ValueError('Enter a SELECT query (maximum 20,000 characters).')
    sql, intent = query_from_input(sql)
    mask = Mask(sql)
    original = mask.tree.sql(dialect='postgres')
    with connect() as conn:
        configure(conn)
        if not (conn.info.dbname == 'querylab' and conn.info.host in {'127.0.0.1', 'localhost'}
                and conn.info.port == 55432) and os.getenv('ALLOW_TEST_DATABASE_BENCHMARK') != '1':
            raise ValueError('Runtime benchmarking is enabled only for the synthetic demo. Use Analyze structure for metadata-only production analysis, or explicitly enable a separate test database with ALLOW_TEST_DATABASE_BENCHMARK=1.')
        plan = explain(conn, original)['Plan']
        graph = gnn.analyze(plan)
        from sqlglot import exp
        ordered = any(isinstance(n, (exp.Order, exp.Limit, exp.Offset)) for n in mask.tree.walk())
        options, seen = {}, {mask.sql}
        if not ordered:
            for action in ('inline', 'deduplicate', 'combined'):
                rewritten = local_rewrite(mask.sql, action)
                if rewritten not in seen:
                    options[action] = rewritten
                    seen.add(rewritten)
        actions = (['ai'] if data.get('use_ai', True) and not ordered else []) + [
            a for a in ('combined', 'inline', 'deduplicate') if a in options] + ['keep']
        # New namespace: AI now selects constrained candidates rather than free SQL.
        state = 'rewrite_v2|' + context(mask.sql, graph)
        action, decision = agent.choose(state, actions)
        try:
            if action == 'ai':
                masked_candidate, reason, engine = optimize(mask.sql, graph, True)
            else:
                masked_candidate = options.get(action, mask.sql)
                reason = ('RL selected: ' + LABELS[action] + '. ' + decision)
                engine = 'RL + local rules + prototype GNN'
            candidate = mask.restore(masked_candidate)
            if action == 'keep':
                candidate = original
            if any(isinstance(n, (exp.Order, exp.Limit, exp.Offset)) for n in select_only(candidate).walk()):
                if action != 'keep':
                    raise ValueError('Rewrite introduced ordering or limits; rejected to preserve result semantics.')
            metrics = compare(conn, original, candidate)
        except Exception:
            # Invalid/failed proposals receive a negative reward, never a speedup reward.
            if action != 'keep':
                agent.learn(state, action, -1)
            raise
    learning = agent.learn(state, action, runtime_reward(metrics, candidate != original))
    learning['decision'] = decision
    if action != 'ai' and graph:
        top=gnn.explain(graph)[0]
        reason += ' Plan evidence: ' + top['reason']
    history.add(original, plan, metrics['original']['execution_ms'])
    return dict(masked_query=mask.sql, masked_optimized=masked_candidate,
                   optimized_query=candidate, explanation=reason, engine=engine,
                   graph=graph, metrics=metrics, changed=candidate != original,
                   total_ms=round((perf_counter() - started) * 1000, 1), rl=learning,
                   gnn_explanations=gnn.explain(graph), intent=intent)


@app.post('/api/optimize')
def run():
    try:
        return jsonify(optimize_query(request.get_json()))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        # Database/parser messages can contain SQL or credentials; keep errors local and generic.
        return jsonify(error='Could not run the query. Check PostgreSQL, table/column names, and the 10-second query limit.'), 400


@app.get('/api/history')
def get_history():
    return jsonify(records=history.list())


@app.post('/api/history')
def import_history():
    try:
        records = request.get_json().get('records', [])
        if not isinstance(records, list) or not 1 <= len(records) <= 50:
            raise ValueError('Import 1-50 JSON log records at a time.')
        # Validate the entire batch before writing any record.
        for record in records:
            Mask(record['query'])
            scrub_plan(record['plan'])
            from history import number
            number(record.get('duration_ms', 0))
        ids = [history.add(r['query'], r['plan'], r.get('duration_ms', 0)) for r in records]
        return jsonify(imported=len(ids), ids=ids, privacy='Only masked SQL, structural hashes and allowlisted numeric plan metadata were saved.')
    except Exception:
        return jsonify(error='Invalid log batch. Each record needs query, plan and optional nonnegative duration_ms.'), 400


@app.post('/api/advice')
def advice():
    try:
        query, intent = query_from_input(request.get_json().get('query', '').strip())
        mask = Mask(query)
        with connect() as conn:
            configure(conn)
            graph = gnn.analyze(explain(conn, mask.tree.sql(dialect='postgres'))['Plan'])
            recommendations = recommend(conn, query)
        kinds = [kind for kind in ('index', 'range', 'hash') if any(r['kind'] == kind
            and not r.get('already_present', False) for r in recommendations)]
        state = 'structure|' + context(mask.sql, graph)
        action, decision = agent.choose(state, kinds + ['structure_keep'])
        token = uuid.uuid4().hex
        if len(proposals) >= 100:
            proposals.pop(next(iter(proposals)))
        proposals[token] = dict(state=state, action=action, recommendations=recommendations, approved=False, simulated=False)
        return jsonify(token=token, action=LABELS[action], decision=decision,
            recommendations=recommendations, gnn_explanations=gnn.explain(graph), graph=graph,
            intent=intent, historical_evidence=history.evidence(query),
            mode='Metadata only: EXPLAIN without ANALYZE; no source result rows were read.')
    except Exception:
        return jsonify(error='Could not analyze this query. Check its syntax and referenced tables. No source data was modified.'), 400


@app.post('/api/simulate')
def run_simulation():
    try:
        proposal = proposals[request.get_json()['token']]
        result = simulate(proposal['action'])
        learning = agent.learn(proposal['state'], proposal['action'], result['reward'])
        proposal.update(simulated=True, simulation=result)
        return jsonify(simulation=result, rl=learning, recommendations=proposal['recommendations'])
    except Exception:
        return jsonify(error='Simulation unavailable. Start the sandbox with docker compose up -d --build --wait. Source tables were not changed.'), 400


@app.post('/api/diagnose')
def diagnose_question():
    try:
        from diagnosis import diagnose
        return jsonify(diagnose(request.get_json(), gnn, agent, history, optimize_query))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Could not diagnose this workload. Check PostgreSQL and the report SQL. No source tables were changed.'), 400


@app.post('/api/approve')
def approve():
    try:
        token = request.get_json()['token']
        proposal = proposals[token]
        if not proposal['simulated']:
            raise ValueError('Simulate this proposal before approving it.')
        proposal['approved'] = True
        return jsonify(approved=True, applied=False, review_package=proposal['recommendations'],
                       message='Approved for manual review only. No source DDL is executed by this app.')
    except Exception:
        return jsonify(error='A successfully simulated proposal is required.'), 400


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
