"""Small message-passing GNN, trained on synthetic plan graphs (prototype only).

Two trained graph-convolution layers and a logistic readout.
No production-trained accuracy is claimed. Numeric plan features only.
"""
import numpy as np

OPERATORS = {'Seq Scan', 'Index Scan', 'Index Only Scan', 'Bitmap Heap Scan',
             'Bitmap Index Scan', 'Nested Loop', 'Hash Join', 'Merge Join',
             'Sort', 'Aggregate', 'Hash', 'Limit', 'Gather', 'Result',
             'CTE Scan', 'Append', 'Merge Append', 'Materialize', 'Other'}


class PlanGNN:
    def __init__(self):
        rng = np.random.default_rng(42)
        self.w1 = rng.normal(0, .6, (4, 12))
        self.w2 = rng.normal(0, .4, (12, 8))
        graphs, adjacency, labels = [], [], []
        for _ in range(150):
            x = rng.random((8, 4))
            a = np.eye(8)
            for i in range(1, 8):
                parent = rng.integers(i)
                a[i, parent] = a[parent, i] = 1
            graphs.append(x)
            adjacency.append(a / a.sum(axis=1, keepdims=True))
            labels.append((x[:, 0] > .55).astype(float))
        x, a, y = np.array(graphs), np.array(adjacency), np.array(labels)
        self.readout = np.zeros(13)
        for _ in range(500):
            ax = a @ x
            z1 = ax @ self.w1
            h1 = np.maximum(0, z1)
            ah1 = a @ h1
            z2 = ah1 @ self.w2
            h2 = np.maximum(0, z2)
            h = np.concatenate([x, h2, np.ones((*y.shape, 1))], axis=2)
            error = (self.sigmoid(h @ self.readout) - y) / y.size
            grad_readout = h.reshape(-1,13).T @ error.ravel()
            dz2 = error[...,None] * self.readout[4:12] * (z2 > 0)
            grad_w2 = ah1.reshape(-1,12).T @ dz2.reshape(-1,8)
            dz1 = (a.transpose(0,2,1) @ (dz2 @ self.w2.T)) * (z1 > 0)
            grad_w1 = ax.reshape(-1,4).T @ dz1.reshape(-1,12)
            self.readout -= .3 * grad_readout
            self.w1 -= .1 * grad_w1
            self.w2 -= .1 * grad_w2

    @staticmethod
    def sigmoid(x):
        return 1 / (1 + np.exp(-np.clip(x, -30, 30)))

    def embed(self, x, a):
        a = a / a.sum(axis=1, keepdims=True)
        h = np.maximum(0, a @ x @ self.w1)
        h = np.maximum(0, a @ h @ self.w2)
        return np.column_stack([x, h, np.ones(len(x))])

    def analyze(self, plan):
        nodes, edges, parents, depths = [], [], [], []
        def visit(node, parent=None, depth=0):
            i = len(nodes)
            nodes.append(node)
            parents.append(parent)
            depths.append(depth)
            if parent is not None:
                edges.append((parent, i))
            for child in node.get('Plans', []):
                visit(child, i, depth + 1)
        visit(plan)
        cost = max(plan.get('Total Cost', 1), 1)
        x = np.array([[min(n.get('Total Cost', 0) / cost, 1),
                       min(np.log1p(n.get('Plan Rows', 0)) / 20, 1),
                       float(n.get('Node Type') == 'Seq Scan'),
                       float('Join' in n.get('Node Type', '') or n.get('Node Type') == 'Nested Loop')]
                      for n in nodes])
        a = np.eye(len(nodes))
        for i, j in edges:
            a[i, j] = a[j, i] = 1
        scores = self.sigmoid(self.embed(x, a) @ self.readout)
        # Only fixed operator labels and numbers are eligible for model input.
        return [dict(node=i, parent=parents[i], depth=depths[i], operator=n.get('Node Type') if n.get('Node Type') in OPERATORS else 'Other',
                     rows=n.get('Plan Rows', 0), cost=n.get('Total Cost', 0),
                     score=round(float(scores[i]), 3)) for i, n in enumerate(nodes)]

    def explain(self, graph):
        candidates = sorted(graph, key=lambda n: n['score'], reverse=True)[:3]
        tips = {'Seq Scan': 'A full scan may benefit from selective composite indexes.',
                'CTE Scan': 'Materialized CTEs may prevent filter pushdown.',
                'Sort': 'Sorting can add work; inspect ordering and index coverage.',
                'Nested Loop': 'Repeated inner scans may benefit from an index on the join key.',
                'Append': 'Check whether partition pruning excludes unrelated partitions.'}
        return [dict(node=n['node'], reason=f"{n['operator']} at node {n['node']} has GNN score {n['score']:.3f}, estimated rows {n['rows']} and planner cost {n['cost']}. " + tips.get(n['operator'], 'Inspect this operator and its child operations for concentrated work.'),
                     evidence=n, model='Synthetic-trained prototype; score is not calibrated probability.') for n in candidates]
