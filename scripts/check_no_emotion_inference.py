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

#: A line may opt out with `# i6-ok: <reason>`. Used for *negative*
#: declarations — publishing that we do not infer emotion is useful to an
#: auditor, and banning the word would delete the disclosure. Every
#: exemption is printed on each run so they cannot pile up unnoticed.
EXEMPT = re.compile(r"#\s*i6-ok:\s*(\S.*)$")


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


def check_file(path: pathlib.Path) -> tuple[list[tuple[int, str]], list[str]]:
    """Return (violations, exemptions) for one file."""
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    docstrings = _docstring_nodes(tree)
    hits: list[tuple[int, str]] = []
    exemptions: list[str] = []

    def _exempt(start: int, end: int) -> bool:
        """Look for the marker on the node's own lines, or the line above it.

        A field is usually annotated by a comment on the preceding line, and a
        multi-line string carries its marker at the end — so a single-line check
        would miss both and push people towards deleting the disclosure instead.
        """
        for lineno in range(max(1, start - 1), min(end, len(lines)) + 1):
            match = EXEMPT.search(lines[lineno - 1])
            if match is not None:
                exemptions.append(f"{path}:{lineno}: {match.group(1).strip()}")
                return True
        return False

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
                lineno = getattr(node, "lineno", 0)
                end = getattr(node, "end_lineno", None) or lineno
                if not _exempt(lineno, end):
                    hits.append((lineno, text[:80]))
    return hits, exemptions


def main() -> int:
    roots = [pathlib.Path(a) for a in sys.argv[1:]] or [pathlib.Path("app")]
    violations: list[str] = []
    exemptions: list[str] = []

    for root in roots:
        for path in sorted(root.rglob("*.py")):
            hits, exempt = check_file(path)
            violations.extend(f"{path}:{lineno}: {token!r}" for lineno, token in hits)
            exemptions.extend(exempt)

    if exemptions:
        print(f"I6 exemptions in force ({len(exemptions)}) — review these:")
        for e in exemptions:
            print(f"  {e}")
        print()

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
