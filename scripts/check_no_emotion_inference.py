#!/usr/bin/env python3
"""Invariant I6 guard: no emotion or sentiment inference in the EU code path.

Customer-facing emotion recognition is a high-risk AI system under the EU AI Act
(Art. 50(3), Annex III) as of 2026-08-02. Shipping it would pull this product
into conformity assessment, CE marking and EU database registration. Routing
uses deterministic ``urgency`` instead — see
``docs/reference/eu-ai-act-obligations.md``.

A plain ``grep`` cannot enforce this. The reason we avoid sentiment has to be
written down, in comments and docstrings, next to the code it constrains — and a
grep flags that documentation as a violation. Worse, a team that gets used to a
noisy guard eventually deletes the explanation to make CI green, which is
exactly backwards.

So this checks *code*, not prose: identifiers, attributes, arguments, keywords,
class and function names, and non-docstring string literals. Comments and
docstrings may discuss the invariant freely.

Exit 0 when clean, 1 on violation.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

BANNED = re.compile(r"sentiment|emotion", re.IGNORECASE)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id() of every string node that is a docstring, so we can ignore them."""
    ignored: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ignored.add(id(body[0].value))
    return ignored


def check_file(path: pathlib.Path) -> list[tuple[int, str]]:
    """Return (lineno, offending token) for each code-level use."""
    tree = ast.parse(path.read_text(), filename=str(path))
    docstrings = _docstring_nodes(tree)
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.Name):
            candidates.append(node.id)
        elif isinstance(node, ast.Attribute):
            candidates.append(node.attr)
        elif isinstance(node, ast.arg) or isinstance(node, ast.keyword) and node.arg:
            candidates.append(node.arg)
        elif isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            candidates.append(node.name)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            candidates.append(node.value)

        for text in candidates:
            if BANNED.search(text):
                hits.append((getattr(node, "lineno", 0), text[:80]))
    return hits


def main() -> int:
    roots = [pathlib.Path(a) for a in sys.argv[1:]] or [pathlib.Path("app")]
    violations: list[str] = []

    for root in roots:
        for path in sorted(root.rglob("*.py")):
            for lineno, token in check_file(path):
                violations.append(f"{path}:{lineno}: {token!r}")

    if violations:
        print("Invariant I6 violated — emotion/sentiment inference in code:")
        for v in violations:
            print(f"  {v}")
        print("\nUse deterministic `urgency` instead. See docs/reference/eu-ai-act-obligations.md")
        return 1

    print(f"I6 clean — no emotion inference in code across {len(roots)} root(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
