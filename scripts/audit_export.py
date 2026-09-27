#!/usr/bin/env python3
"""Conservative local export scan; reports locations, never matched secret values."""
import argparse
import ast
import json
from pathlib import Path
import re

PATTERNS = {
    'source-specific label': r'(?i)fra[m]e[12]|holo[n]ograph|brian[k]errigan|inspector[s]lap|precision\s+innovations|ZP[2]-\d+|P2[B]-\d+',
    'private machine path': r'/Use[r]s/|/private[/]',
    'email address': r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
    'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'credential-shaped string': r'\b(?:sk_live_|sk-ant-)[A-Za-z0-9_-]{12,}',
    'inherited approval': r'APPROVED_BY_OPERATOR_[0-9]|["\x27]approved_at["\x27]\s*:\s*["\x27]20[0-9]{2}',
}
SKIP = {'.git', '__pycache__', '.venv', 'venv', 'workspace', 'workspaces'}


def audit(root):
    issues = []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(part in SKIP for part in rel.parts):
            continue
        if path.is_symlink():
            issues.append({'path': str(rel), 'issue': 'symlink not allowed'})
            continue
        if not path.is_file():
            continue
        if path.name.startswith('.env') or path.suffix in ('.key', '.token', '.pem', '.zip') or path.name == '.DS_Store':
            issues.append({'path': str(rel), 'issue': 'excluded artifact type'})
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            issues.append({'path': str(rel), 'issue': 'unexpected binary file'})
            continue
        for name, pattern in PATTERNS.items():
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(pattern, line):
                    issues.append({'path': str(rel), 'line': number, 'issue': name})
        if path.suffix == '.py':
            try:
                tree = ast.parse(text)
            except SyntaxError:
                issues.append({'path': str(rel), 'issue': 'Python syntax error'})
                continue
            if rel.parts[0] == 'incubator':
                body = list(tree.body)
                while body and (isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str) or isinstance(body[0], ast.ImportFrom) and body[0].module == '__future__'):
                    body.pop(0)
                if not body or not isinstance(body[0], ast.Raise):
                    issues.append({'path': str(rel), 'issue': 'archive execution guard absent'})
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    issues = audit(args.root)
    print(json.dumps({'issues': issues, 'passed': not issues, 'note': 'Heuristic scan only; generated workspaces excluded, manual review still required.'}, indent=2))
    return bool(issues)

if __name__ == '__main__':
    raise SystemExit(main())
