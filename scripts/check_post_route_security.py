"""Static regression check for POST route authentication/CSRF coverage.

This deliberately treats login and logout as the only public POST endpoints:
login authenticates credentials, while logout is still covered by the global
CSRF before-request hook. Any new public POST route must be explicitly reviewed.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS = ROOT / "employee_movements" / "blueprints"
PUBLIC_POST_ALLOWLIST = {("auth.py", "login"), ("auth.py", "logout")}
errors = []
post_routes = []

for path in sorted(BLUEPRINTS.glob("*.py")):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        errors.append(f"syntax error in {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
        continue
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [ast.unparse(d) for d in node.decorator_list]
        is_post = any(
            (".post(" in d)
            or ("methods" in d and "POST" in d and ("route(" in d))
            for d in decorators
        )
        if not is_post:
            continue
        key = (path.name, node.name)
        post_routes.append(f"{path.name}:{node.name}")
        if key in PUBLIC_POST_ALLOWLIST:
            continue
        if not any(d == "req" or d.endswith(".req") for d in decorators):
            errors.append(
                f"POST route lacks @req (authentication/CSRF review required): {path.name}:{node.name}"
            )

hooks = (ROOT / "employee_movements" / "hooks.py").read_text(encoding="utf-8")
if "CSRF_EXEMPT_ENDPOINTS = frozenset()" not in hooks:
    errors.append("CSRF exemption allowlist changed; review every exempt POST endpoint")
if "hmac.compare_digest(token, expected)" not in hooks:
    errors.append("global CSRF token comparison changed; review CSRF validation")

print(f"POST_ROUTES_REVIEWED={len(post_routes)}")
if errors:
    print("\n".join(errors))
    raise SystemExit(1)
print("POST_ROUTE_SECURITY=OK")
