"""Architecture checks for the dependency direction of the scaffold."""

import ast
from pathlib import Path

import pytest


@pytest.mark.integration
def test_domain_and_application_are_framework_independent() -> None:
    root = Path(__file__).parents[2] / "src" / "knowledge_system"
    forbidden_prefixes = ("fastapi", "pydantic", "sqlalchemy", "opensearchpy")

    for package in ("domain", "application"):
        for path in (root / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Import | ast.ImportFrom)
            ]
            for node in imports:
                module = (
                    node.module or ""
                    if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                )
                assert not module.startswith(forbidden_prefixes), (
                    f"forbidden import in {path}: {module}"
                )
