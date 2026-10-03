"""Per-request reversible pseudonyms. The mapping never leaves this process."""
import hashlib
import hmac
import secrets
import sqlglot
from sqlglot import exp


def select_only(sql):
    statements = sqlglot.parse(sql, read='postgres')
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError('Enter one SELECT query only.')
    tree = statements[0]
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
                 exp.Command, exp.Into, exp.Lock, exp.Anonymous)
    if any(isinstance(n, forbidden) for n in tree.walk()):
        raise ValueError('Only read-only SELECT queries with built-in SQL functions are supported.')
    return tree


class Mask:
    def __init__(self, sql):
        self.tree = select_only(sql)
        if any(isinstance(n, (exp.Placeholder, exp.Parameter)) for n in self.tree.walk()):
            raise ValueError('Enter a complete SELECT with literal values, not external parameters.')
        self.names, self.values = {}, {}
        literal_tokens = {}
        key = secrets.token_bytes(32)
        tree = self.tree.copy()
        for node in list(tree.walk()):
            node.comments = None
            if isinstance(node, exp.Identifier):
                # PostgreSQL folds unquoted names to lower case.
                name = node.this if node.args.get('quoted') else node.this.lower()
                token = 'id_' + hmac.new(key, name.encode(), hashlib.sha256).hexdigest()[:16]
                self.names[token] = node.copy()
                node.set('this', token)
                node.set('quoted', False)
            elif isinstance(node, (exp.Literal, exp.Boolean, exp.Null)):
                signature = node.sql(dialect='postgres')
                token = literal_tokens.setdefault(signature, 'value_' + str(len(self.values)))
                self.values[token] = node.copy()
                node.replace(exp.Placeholder(this=token))
        self.sql = tree.sql(dialect='postgres')
        # Reject syntax with textual payloads that are not AST identifiers/literals.
        allowed_text = {'this', 'expression'}
        for node in tree.walk():
            if isinstance(node, (exp.Identifier, exp.Placeholder, exp.DataType, exp.Var)):
                continue
            for field, value in node.args.items():
                if isinstance(value, str) and field in allowed_text:
                    raise ValueError('This SQL syntax cannot be safely masked. Use a simpler SELECT.')
        if any(isinstance(n, exp.Var) for n in tree.walk()):
            raise ValueError('Special SQL variables are not supported by the privacy layer.')

    def restore(self, sql):
        tree = select_only(sql)
        if any(isinstance(n, (exp.Literal, exp.Boolean, exp.Null, exp.Parameter)) for n in tree.walk()):
            raise ValueError('AI introduced a new value instead of preserving a masked placeholder.')
        for node in list(tree.walk()):
            if isinstance(node, exp.Identifier):
                if isinstance(node.parent, exp.Placeholder):
                    continue
                if node.this not in self.names:
                    raise ValueError('AI returned an unknown identifier; rewrite rejected.')
                node.replace(self.names[node.this].copy())
            elif isinstance(node, exp.Placeholder):
                token = node.this.name if isinstance(node.this, exp.Expression) else node.this
                if token not in self.values:
                    raise ValueError('AI returned an unknown value; rewrite rejected.')
                node.replace(self.values[token].copy())
        return tree.sql(dialect='postgres')
