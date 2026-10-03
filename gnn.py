"""Small message-passing GNN, trained on synthetic plan graphs (prototype only).

Two fixed random graph-convolution layers and a trained logistic readout.
No production-trained accuracy is claimed. Numeric plan features only.
"""
import numpy as np


class PlanGNN:
    def __init__(self):
        rng = np.random.default_rng(42)
        self.w1 = rng.normal(0, .6, (4, 12))
        self.w2 = rng.normal(0, .4, (12, 8))
        features, labels = [], []
        for _ in range(150):
            x = rng.random((8, 4))
            a = np.eye(8)
            for i in range(1, 8):
                parent = rng.integers(i)
                a[i, parent] = a[parent, i] = 1
            features.extend(self.embed(x, a))
            labels.extend((x[:, 0] > .55).astype(float))
        h, y = np.array(features), np.array(labels)
        self.readout = np.zeros(h.shape[1])
        for _ in range(500):
            p = self.sigmoid(h @ self.readout)
            self.readout -= .3 * h.T @ (p - y) / len(y)

    @staticmethod
    def sigmoid(x):
        return 1 / (1 + np.exp(-np.clip(x, -30, 30)))

    def embed(self, x, a):
        a = a / a.sum(axis=1, keepdims=True)
        h = np.maximum(0, a @ x @ self.w1)
        h = np.maximum(0, a @ h @ self.w2)
        return np.column_stack([x, h, np.ones(len(x))])

    def analyze(self, plan):
        nodes, edges = [], []
        def visit(node, parent=None):
            i = len(nodes)
            nodes.append(node)
            if parent is not None:
                edges.append((parent, i))
            for child in node.get('Plans', []):
                visit(child, i)
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
        known = {'Seq Scan', 'Index Scan', 'Index Only Scan', 'Bitmap Heap Scan',
                 'Bitmap Index Scan', 'Nested Loop', 'Hash Join', 'Merge Join',
                 'Sort', 'Aggregate', 'Hash', 'Limit', 'Gather', 'Result'}
        return [dict(node=i, operator=n.get('Node Type') if n.get('Node Type') in known else 'Other',
                     rows=n.get('Plan Rows', 0), cost=n.get('Total Cost', 0),
                     score=round(float(scores[i]), 3)) for i, n in enumerate(nodes)]
