from rl import RewriteAgent, context, runtime_reward
from privacy import Mask


def test_learns_explores_and_persists(tmp_path):
    path = tmp_path / 'rl.sqlite3'
    agent = RewriteAgent(path)
    assert agent.choose('state', ['inline', 'keep'])[0] == 'inline'
    agent.learn('state', 'inline', .8)
    assert agent.choose('state', ['inline', 'keep'])[0] == 'keep'
    agent.learn('state', 'keep', 0)
    restored = RewriteAgent(path)
    assert restored.choose('state', ['inline', 'keep'])[0] == 'inline'
    result = restored.learn('state', 'inline', .6)
    assert result['q_value'] == .7 and result['action_trials'] == 2


def test_bad_actions_lose_preference(tmp_path):
    agent = RewriteAgent(tmp_path / 'rl.sqlite3')
    agent.learn('state', 'inline', -.5)
    agent.learn('state', 'keep', 0)
    assert agent.choose('state', ['inline', 'keep'])[0] == 'keep'
    assert agent.choose('other', ['keep'])[0] == 'keep'


def test_reward_noise_and_regression():
    def metrics(a, b):
        return {'original': {'execution_ms': a}, 'optimized': {'execution_ms': b}}
    assert runtime_reward(metrics(100, 20), True) == .8
    assert runtime_reward(metrics(100, 150), True) == -.5
    assert runtime_reward(metrics(1, .99), True) == 0
    assert runtime_reward(metrics(100, 20), False) == 0


def test_context_is_private_and_generalizes():
    graph = [{'rows': 200000, 'score': .7}]
    a = context(Mask("SELECT salary FROM private_people WHERE age IN (25,25)").sql, graph)
    b = context(Mask("SELECT price FROM products WHERE stock IN (10,10)").sql, graph)
    assert a == b
    assert 'private' not in a and '25' not in a
