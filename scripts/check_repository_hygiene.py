"""Check repository structure and release metadata using only the standard library.

The checks are deliberately conservative: they flag duplicated test source,
late module-level imports inside the application package, and version drift in
release-critical files without rewriting source automatically.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "employee_movements"
TEST_ROOTS = (ROOT / "tests", ROOT / "contract_tests")
VERSIONED_CSS_HEADERS = (
    PACKAGE / "static" / "css" / "app.css",
    PACKAGE / "static" / "css" / "design-system-cyan.css",
    PACKAGE / "static" / "css" / "ui-components.css",
    PACKAGE / "static" / "css" / "pages" / "mission-report-print.css",
)


def _is_module_docstring(node: ast.stmt, first_node: ast.stmt | None) -> bool:
    return (
        node is first_node
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def find_late_module_imports() -> list[str]:
    """Find imports placed after executable module-level statements in app code."""
    findings: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(f"cannot parse {path.relative_to(ROOT)}: {exc}")
            continue

        seen_statement = False
        first_node = tree.body[0] if tree.body else None
        for node in tree.body:
            if _is_module_docstring(node, first_node):
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if seen_statement and not (
                    isinstance(node, ast.ImportFrom) and node.module == "__future__"
                ):
                    findings.append(
                        f"late module-level import in {path.relative_to(ROOT)}:{node.lineno}"
                    )
                continue
            seen_statement = True
    return findings


def find_duplicate_test_sources() -> list[str]:
    """Find byte-identical test modules copied between tests/ and contract_tests/."""
    hashes: dict[str, list[Path]] = defaultdict(list)
    for test_root in TEST_ROOTS:
        if not test_root.is_dir():
            continue
        for path in sorted(test_root.rglob("test_*.py")):
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                return [f"cannot read test source {path.relative_to(ROOT)}: {exc}"]
            hashes[digest].append(path)

    findings: list[str] = []
    for paths in hashes.values():
        roots = {path.relative_to(ROOT).parts[0] for path in paths}
        if len(roots) > 1:
            names = ", ".join(str(path.relative_to(ROOT)) for path in paths)
            findings.append(f"duplicate test sources across suites: {names}")
    return findings


def find_release_metadata_drift() -> list[str]:
    """Ensure the repository's release-critical version markers agree."""
    findings: list[str] = []
    try:
        version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
        package_version = None
        for node in package_tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
                    package_version = ast.literal_eval(node.value)
                    break
        generic_manifest = json.loads((ROOT / "REVIEW_MANIFEST.json").read_text(encoding="utf-8"))
        versioned_candidates = sorted(ROOT.glob(f"REVIEW_MANIFEST_v{version}_round*.json"))
        if len(versioned_candidates) != 1:
            raise ValueError(
                f"expected one round-qualified manifest for {version}, found {len(versioned_candidates)}"
            )
        versioned_manifest_path = versioned_candidates[0]
        versioned_manifest = json.loads(versioned_manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, SyntaxError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        return [f"release metadata could not be read: {exc}"]

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        findings.append(f"VERSION.md is not a semantic three-part version: {version!r}")
    if pyproject.get("project", {}).get("version") != version:
        findings.append("pyproject.toml version differs from VERSION.md")
    if package_version != version:
        findings.append("employee_movements/__init__.py __version__ differs from VERSION.md")
    if generic_manifest.get("version") != version:
        findings.append("REVIEW_MANIFEST.json version differs from VERSION.md")
    if versioned_manifest.get("version") != version:
        findings.append(f"{versioned_manifest_path.name} has a stale version field")

    for path in VERSIONED_CSS_HEADERS:
        try:
            header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:4])
        except OSError as exc:
            findings.append(f"cannot read {path.relative_to(ROOT)}: {exc}")
            continue
        if f"v{version}" not in header:
            findings.append(f"version marker in {path.relative_to(ROOT)} differs from {version}")
    return findings


def collect_findings() -> list[str]:
    return (
        find_late_module_imports()
        + find_duplicate_test_sources()
        + find_release_metadata_drift()
    )


def main() -> int:
    findings = collect_findings()
    print(f"APP_PACKAGE_PY_FILES={len(list(PACKAGE.rglob('*.py')))}")
    print(f"TEST_SUITES_SCANNED={len(TEST_ROOTS)}")
    if findings:
        print("REPOSITORY_HYGIENE=FAILED")
        print("\n".join(findings))
        return 1
    print("REPOSITORY_HYGIENE=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
