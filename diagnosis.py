"""Small, grounded performance-question orchestration; questions stay local."""
from privacy import Mask
from workloads import query_from_input
from database import connect, configure, explain
from recommendations import recommend
from simulation import simulate
from rl import context, LABELS


def plan_facts(graph):
    scans = [n for n in graph if n['operator'] == 'Seq Scan']
    nested = sum(n['operator'] == 'Nested Loop' for n in graph)
    ctes = sum(n['operator'] == 'CTE Scan' for n in graph)
    return ('Current EXPLAIN metadata: %d sequential scans (largest estimated output %s rows), '
            '%d nested-loop operators and %d CTE scans. This is not proof of a timeout cause.' %
            (len(scans), max((n['rows'] for n in scans), default=0), nested, ctes))


def diagnose(data, gnn, agent, history, optimize_query):
    question = data.get('question', '').strip()
    if not question or len(question) > 2000:
        raise ValueError('Enter a performance question (maximum 2,000 characters).')
    associated = data.get('query', '').strip()
    query, recent = history.workload(question, associated)
    intent = 'historical_execution'
    mask = Mask(query)
    with connect() as conn:
        configure(conn)
        graph = gnn.analyze(explain(conn, mask.tree.sql(dialect='postgres'))['Plan'])
        recommendations = recommend(conn, query)
    historical_graphs = [gnn.analyze(r['plan']) for r in recent['recent_plan_summaries']]
    answer = ['Selected past execution #%d from %d relevant recorded executions for this database. The original SQL and dates are retained.' % (recent['selected_record_id'], recent['matched_executions']),
              plan_facts(graph),
              'Recent masked history: %d executions of this exact query. Historical median %.3f ms. %s' % (recent['structurally_similar_logs'], recent['median_logged_duration_ms'], recent['scope'])]
    answer.append('The %d recent historical plans contain %d sequential scans, %d nested loops and %d CTE scans in total.' % (len(historical_graphs), sum(n['operator']=='Seq Scan' for g in historical_graphs for n in g), sum(n['operator']=='Nested Loop' for g in historical_graphs for n in g), sum(n['operator']=='CTE Scan' for g in historical_graphs for n in g)))
    result = optimize_query({'query': query, 'use_ai': bool(data.get('use_ai', False))})
    m = result['metrics']
    answer.append('Local test database: original %.3f ms; selected query %.3f ms (%+.2f%% improvement). Result equivalence was checked inside PostgreSQL.' %
                  (m['original']['execution_ms'], m['optimized']['execution_ms'], m['improvement_pct']))
    answer.append(result['explanation'])
    kinds = [kind for kind in ('index', 'range', 'hash') if any(r['kind'] == kind and not r.get('already_present', False) for r in recommendations)]
    state = 'structure|' + context(mask.sql, graph)
    action, decision = agent.choose(state, kinds + ['structure_keep'])
    simulation_result, simulation_error = None, None
    try:
        simulation_result = simulate(action)
        agent.learn(state, action, simulation_result['reward'])
        answer.append('Separate synthetic sandbox, %s: read %.3f to %.3f ms (%+.2f%%); insert latency change %+.6f ms per row. %s' %
                      (LABELS[action], simulation_result['baseline']['read_ms'], simulation_result['proposed']['read_ms'], simulation_result['read_improvement_pct'], simulation_result['write_latency_delta_ms_per_row'], simulation_result['scope']))
    except Exception:
        simulation_error = 'Sandbox unavailable; no structural performance estimate is claimed.'
        answer.append(simulation_error)
    improvements = [dict(title='SQL rewrite' if result['changed'] else 'Keep the original SQL',
        detail='Historical plan evidence: %d CTE scans and %d sequential scans across %d saved plans. %s' %
               (sum(n['operator']=='CTE Scan' for g in historical_graphs for n in g),
                sum(n['operator']=='Seq Scan' for g in historical_graphs for n in g), len(historical_graphs), result['explanation']),
        improvement_pct=m['improvement_pct'] if result['changed'] else None,
        scope='Measured on the selected historical query in the local test database; result equivalence verified.',
        before_ms=m['original']['execution_ms'], after_ms=m['optimized']['execution_ms'])]
    if simulation_result and action != 'structure_keep':
        improvements.append(dict(title=LABELS[action], improvement_pct=simulation_result['read_improvement_pct'],
            detail='Synthetic read benchmark; insert latency change %+.6f ms per row.' % simulation_result['write_latency_delta_ms_per_row'],
            scope=simulation_result['scope']))
    for recommendation in recommendations:
        if recommendation.get('already_present') or recommendation['kind'] == action:
            continue
        improvements.append(dict(title=LABELS[recommendation['kind']] + ' · ' + recommendation['table'], detail=recommendation['reason'],
                                 improvement_pct=None, scope='Recommendation only; improvement not measured for this query.'))
    answer.append('These are separate experiments; their gains cannot be added. No timeout was reproduced or diagnosed from timings alone. No source tables were altered. AI receives masked SQL and numeric/operator metadata only; no raw identifiers, literals or result rows are sent to it. The question is interpreted locally.')
    return dict(answer=answer, question=question, report_query=query, intent=intent,
                historical_evidence=recent, recommendations=recommendations, result=result, improvements=improvements,
                simulation=simulation_result, simulation_error=simulation_error, structural_decision=decision)
