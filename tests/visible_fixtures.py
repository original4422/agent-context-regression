"""Complete only the dependency hook, keeping the shared checkpoint executable."""
import ast
from context_regression.tasks import BUILTIN_TASKS


def reference(version):
    tree = ast.parse((BUILTIN_TASKS / 'visible-policy-a/snapshot/plan.py').read_text())
    hook = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_dependencies_satisfied')
    expression = 'all(item in completed for item in needs)' if version == 'a' else 'all(item in completed or item in selected for item in needs)'
    hook.body = ast.parse('return ' + expression).body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + '\n'


SOLUTIONS = {f'visible-policy-{version}':reference(version) for version in ('a','b')}
