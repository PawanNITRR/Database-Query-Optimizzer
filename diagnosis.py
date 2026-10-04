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
    query, intent = query_from_input(associated or question)
    mask = Mask(query)
    recent = history.evidence(query)
    with connect() as conn:
        configure(conn)
        graph = gnn.analyze(explain(conn, mask.tree.sql(dialect='postgres'))['Plan'])
        recommendations = recommend(conn, query)
    answer = [('Analyzed your associated SQL.' if associated else
               'Matched the question to the %s demo report. This is a fixed workload, not automatic dashboard discovery.' % intent),
              plan_facts(graph),
              'Recent masked history: %d structurally similar records. %s' %
              (recent['structurally_similar_logs'], recent['scope'])]
    if recent['median_logged_duration_ms'] is not None:
        answer.append('Their median recorded runtime was %.3f ms.' % recent['median_logged_duration_ms'])
    summaries = recent['recent_plan_summaries']
    if summaries:
        answer.append('The %d most recent matching masked plans contain %d sequential scan operators, %d nested loops and %d CTE scans in total. Structural similarity does not establish that these are the same dashboard.' %
                      (len(summaries), sum(r['operators'].count('Seq Scan') for r in summaries),
                       sum(r['operators'].count('Nested Loop') for r in summaries), sum(r['operators'].count('CTE Scan') for r in summaries)))
    else:
        answer.append('No recent matching plans were available; this diagnosis uses the current EXPLAIN plan.')
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
    answer.append('These are separate experiments; their gains cannot be added. No timeout was reproduced or diagnosed from timings alone. No source tables were altered. AI receives masked SQL and numeric/operator metadata only; no raw identifiers, literals or result rows are sent to it. The question is interpreted locally.')
    return dict(answer=answer, question=question, report_query=query, intent=intent,
                historical_evidence=recent, recommendations=recommendations, result=result,
                simulation=simulation_result, simulation_error=simulation_error, structural_decision=decision)
