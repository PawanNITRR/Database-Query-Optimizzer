"""One-step reinforcement learning: a contextual UCB bandit over rewrite actions.

Q(s,a) is the mean observed reward. Only coarse structural features and numeric
rewards persist; SQL, names, literals, credentials and result rows never do.
"""
import math
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from sqlglot import exp
from privacy import select_only

LABELS = {'keep': 'Keep original', 'inline': 'Inline simple CTE',
          'deduplicate': 'Remove duplicate IN values', 'combined': 'Combine SQL rules',
          'ai': 'Ask local AI for a rewrite'}


def context(sql, graph):
    tree = select_only(sql)
    rows = max((node['rows'] for node in graph), default=0)
    score = max((node['score'] for node in graph), default=0)
    return '|'.join(map(str, ['v1', min(len(list(tree.find_all(exp.Join))), 4),
        int(any(c.args.get('materialized') is True for c in tree.find_all(exp.CTE))),
        int(bool(list(tree.find_all(exp.In)))),
        min(int(math.log10(max(rows, 1))), 7), int(score >= .5)]))


class RewriteAgent:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('RL_STATE_PATH',
            str(Path(__file__).parent / 'data' / 'rl.sqlite3')))

    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute('CREATE TABLE IF NOT EXISTS policy (context TEXT, action TEXT, trials INTEGER, q REAL, PRIMARY KEY(context, action))')
        return conn

    def choose(self, state, actions):
        with closing(self.db()) as conn:
            records = {a: (n, q) for a, n, q in conn.execute(
                'SELECT action, trials, q FROM policy WHERE context=?', (state,))}
        # Try each eligible strategy before trusting its estimated reward.
        untried = next((a for a in actions if a not in records), None)
        if untried:
            return untried, 'Exploration: trying an untested action for this query structure.'
        total = sum(records[a][0] for a in actions)
        action = max(actions, key=lambda a: records[a][1] +
                     .15 * math.sqrt(math.log(total + 1) / records[a][0]))
        return action, 'UCB policy: balances measured reward with exploration of less-tested actions.'

    def learn(self, state, action, reward):
        reward = max(-1.0, min(1.0, float(reward)))
        conn = self.db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute('SELECT trials, q FROM policy WHERE context=? AND action=?',
                                    (state, action)).fetchone()
            trials, q = previous or (0, 0.0)
            trials += 1
            q += (reward - q) / trials
            conn.execute('INSERT INTO policy VALUES (?, ?, ?, ?) ON CONFLICT(context, action) DO UPDATE SET trials=excluded.trials, q=excluded.q',
                         (state, action, trials, q))
            conn.commit()
            return {'action': action, 'label': LABELS[action], 'reward': round(reward, 4),
                    'q_value': round(q, 4), 'action_trials': trials,
                    'context': state, 'algorithm': 'Contextual UCB bandit'}
        finally:
            conn.close()


def runtime_reward(metrics, changed):
    old = metrics['original']['execution_ms']
    new = metrics['optimized']['execution_ms']
    # No reward for timing noise or two runs of the same SQL.
    if not changed or old <= 0 or abs(old - new) < max(.05, old * .03):
        return 0.0
    return max(-1.0, min(1.0, (old - new) / old))
