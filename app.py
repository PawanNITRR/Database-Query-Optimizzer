from flask import Flask, jsonify, render_template, request
from time import perf_counter
from privacy import Mask, select_only
from gnn import PlanGNN
from optimizer import optimize, ai_available, local_rewrite
from rl import RewriteAgent, context, runtime_reward, LABELS
from database import connect, configure, explain, compare

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024
gnn = PlanGNN()
agent = RewriteAgent()


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
            state = context(mask.sql, graph)
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
        return jsonify(masked_query=mask.sql, masked_optimized=masked_candidate,
                       optimized_query=candidate, explanation=reason, engine=engine,
                       graph=graph, metrics=metrics, changed=candidate != original,
                       total_ms=round((perf_counter() - started) * 1000, 1), rl=learning)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        # Database/parser messages can contain SQL or credentials; keep errors local and generic.
        return jsonify(error='Could not run the query. Check PostgreSQL, table/column names, and the 10-second query limit.'), 400


@app.post('/api/chat')
def chat():
    """Answer a natural-language question using only this request's masked plan data."""
    started = perf_counter()
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        sql = data.get('query', '').strip()
        if not message or len(message) > 2000:
            raise ValueError('Ask a question (maximum 2,000 characters).')
        if not sql:
            raise ValueError('Add a SELECT query above so I can inspect its execution plan.')

        # Reuse the same guarded analysis and measured comparison as the dashboard.
        # The chat turn itself is never forwarded to the AI model.
        original = Mask(sql)
        with connect() as conn:
            configure(conn)
            plan = explain(conn, original.tree.sql(dialect='postgres'))['Plan']
            graph = gnn.analyze(plan)
            from sqlglot import exp
            ordered = any(isinstance(n, (exp.Order, exp.Limit, exp.Offset)) for n in original.tree.walk())
            options, seen = {}, {original.sql}
            if not ordered:
                for action in ('inline', 'deduplicate', 'combined'):
                    rewritten = local_rewrite(original.sql, action)
                    if rewritten not in seen:
                        options[action] = rewritten
                        seen.add(rewritten)
            actions = (['ai'] if data.get('use_ai', False) and not ordered else []) + [
                a for a in ('combined', 'inline', 'deduplicate') if a in options] + ['keep']
            state = context(original.sql, graph)
            action, decision = agent.choose(state, actions)
            if action == 'ai':
                masked_candidate, reason, engine = optimize(original.sql, graph, True)
            else:
                masked_candidate = options.get(action, original.sql)
                reason = ('RL selected: ' + LABELS[action] + '. ' + decision)
                engine = 'RL + local rules + prototype GNN'
            candidate = original.restore(masked_candidate)
            if action == 'keep':
                candidate = original.tree.sql(dialect='postgres')
            metrics = compare(conn, original.tree.sql(dialect='postgres'), candidate)
        learning = agent.learn(state, action, runtime_reward(
            metrics, candidate != original.tree.sql(dialect='postgres')))

        lead = ('I checked your query against the local PostgreSQL plan. ' + reason)
        if graph:
            top = max(graph, key=lambda n: n.get('score', 0))
            evidence = (f"The highest GNN-scored operator is {top['operator']} "
                        f"(estimated {top['rows']} rows, planner cost {top['cost']}, "
                        f"score {top['score']}).")
        else:
            evidence = 'PostgreSQL returned no plan nodes to score.'
        topic = message.casefold()
        if any(word in topic for word in ('index', 'partition', 'shard', 'storage', 'write latency')):
            guidance = ('This prototype does not recommend or simulate indexes, partitioning, sharding, '
                        'storage, or write-latency changes. ')
        elif any(word in topic for word in ('why', 'slow', 'timeout', 'bottleneck')):
            guidance = 'The plan evidence to investigate first is: ' + evidence + ' '
        elif any(word in topic for word in ('explain', 'plan', 'operator', 'gnn')):
            guidance = 'The plan summary is: ' + evidence + ' GNN scores rank plan nodes; they are not proof of savings. '
        elif any(word in topic for word in ('optimize', 'rewrite', 'improve', 'faster')):
            guidance = 'I evaluated the selected rewrite against the original query: ' + reason + ' '
        else:
            guidance = 'I can help with query speed, plan explanations, and rewrites. ' + evidence + ' '
        delta = metrics['improvement_pct']
        if delta > 0:
            outcome = f"The candidate was {delta:.1f}% faster in this comparison."
        elif delta < 0:
            outcome = f"The candidate was {abs(delta):.1f}% slower in this comparison."
        else:
            outcome = 'The measured runtimes were effectively unchanged.'
        question = ' '.join(message.split())
        if len(question) > 180:
            question = question[:177] + '...'
        reply = (f"For “{question}”: {guidance}{lead} {outcome} "
                 f"The RL policy selected {learning['label']} after "
                 f"{learning['action_trials']} observations of this action. These are local measurements, not a "
                 "production-impact or write-latency simulation. No production schema "
                 "changes were applied.")
        return jsonify(reply=reply, optimized_query=candidate, graph=graph,
                       metrics=metrics, engine=engine,
                       total_ms=round((perf_counter() - started) * 1000, 1))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Could not analyze this query. Check PostgreSQL, table/column names, and the 10-second query limit.'), 400


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
