"""Markdown + YAML frontmatter on disk -> `Doc` records. Build spec section 5.

Three shapes live under `kb/`:

* `kb/docs/<area>/<slug>-<version>.md`  one route doc, one `Doc`.
* `kb/errors/<area>.md`                 one markdown table, one `Doc` per row.
* `kb/approved/<name>.md`               an approved answer, `source="approved_answer"`.

Missing subdirectories are tolerated, but a load that finds nothing at all
raises. The corpus is on disk now, so an empty load means a wrong `KB_ROOT`,
which would otherwise present as a system that abstains on every ticket.
"""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from app.state import Doc

# Columns the error tables are written with, lower-cased for matching.
_ERROR_COLUMNS = ("code", "http", "message", "cause", "fix", "versions")


class CorpusError(ValueError):
    """A file under kb/ does not match the section 5 shape."""


def _require(meta: dict, key: str, path: Path) -> str:
    value = meta.get(key)
    if value is None or value == "":
        raise CorpusError(f"{path}: missing frontmatter key {key!r}")
    return str(value)


def _doc_from_post(post: frontmatter.Post, path: Path, source: str) -> Doc:
    meta = post.metadata
    replaced_by = meta.get("replaced_by")
    if replaced_by in ("", "null", "None"):
        replaced_by = None
    return Doc(
        doc_id=_require(meta, "doc_id", path),
        source=meta.get("source", source),
        route=str(meta.get("route") or ""),
        version=_require(meta, "version", path),
        area=_require(meta, "area", path),
        status=meta.get("status", "current"),
        replaced_by=replaced_by,
        error_code=meta.get("error_code"),
        description=_require(meta, "description", path),
        url=str(meta.get("url") or ""),
        text=post.content.strip(),
    )


def _clean_cell(cell: str) -> str:
    """Strip the inline markdown the corpus writes codes in.

    The tables render codes as `` `PAY_4012` ``, but section 5 says the doc_id is
    `payments-errors#PAY_4012` and the planner emits a bare code, so the emphasis
    characters come off here rather than at every lookup site.
    """
    return cell.strip().strip("`*_ ").strip()


def _split_table_row(line: str) -> list[str]:
    """`| a | b |` -> ["a", "b"]."""
    return [_clean_cell(cell) for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def parse_error_table(path: Path) -> list[Doc]:
    """One error-table file -> one `Doc` per table row.

    `doc_id` becomes `<file doc_id>#<CODE>`, `error_code` is the code, `text` is
    the row rendered as prose so the drafter has something readable to cite, and
    `description` is the message column because that is what the semantic index
    embeds.
    """
    post = frontmatter.load(path)
    base = _doc_from_post(post, path, source="doc")

    lines = [ln for ln in post.content.splitlines() if ln.strip().startswith("|")]
    if not lines:
        raise CorpusError(f"{path}: no markdown table found")

    header = [c.lower() for c in _split_table_row(lines[0])]
    missing = [c for c in _ERROR_COLUMNS if c not in header]
    if missing:
        raise CorpusError(f"{path}: error table is missing columns {missing}")

    rows: list[Doc] = []
    for line in lines[1:]:
        cells = _split_table_row(line)
        if _is_separator(cells) or len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        code = row["code"]
        if not code:
            continue
        text = (
            f"{code} ({row['http']}): {row['message']}. "
            f"Cause: {row['cause']}. Fix: {row['fix']}. "
            f"Applies to: {row['versions']}."
        )
        doc = dict(base)
        doc.update(
            doc_id=f"{base['doc_id']}#{code}",
            error_code=code,
            description=row["message"],
            text=text,
        )
        rows.append(Doc(**doc))  # type: ignore[typeddict-item]

    if not rows:
        raise CorpusError(f"{path}: error table has a header but no rows")
    return rows


def parse_route_doc(path: Path) -> Doc:
    """One `kb/docs/<area>/<slug>-<version>.md` file -> one `Doc`."""
    return _doc_from_post(frontmatter.load(path), path, source="doc")


def parse_approved_answer(path: Path) -> Doc:
    """One `kb/approved/<name>.md` file -> one `Doc` tagged `approved_answer`."""
    return _doc_from_post(frontmatter.load(path), path, source="approved_answer")


def load_kb(root: Path) -> list[Doc]:
    """Load every `Doc` under `root`. Missing subdirectories are fine, an empty load is not."""
    root = Path(root)
    docs: list[Doc] = []

    for path in sorted((root / "docs").rglob("*.md")):
        docs.append(parse_route_doc(path))

    for path in sorted((root / "errors").glob("*.md")):
        docs.extend(parse_error_table(path))

    for path in sorted((root / "approved").glob("*.md")):
        docs.append(parse_approved_answer(path))

    seen: dict[str, Path] = {}
    for doc in docs:
        if doc["doc_id"] in seen:
            raise CorpusError(f"duplicate doc_id {doc['doc_id']!r} under {root}")
        seen[doc["doc_id"]] = root

    # 4c change to 4a's file, one behavior only. An empty load used to be fine
    # because 4a and 4a2 ran in parallel and the corpus did not exist yet. The
    # corpus is on disk now, so an empty load means a wrong KB_ROOT, and a wrong
    # KB_ROOT makes the system abstain on every ticket and look like a
    # retrieval bug rather than a path bug.
    if not docs:
        raise CorpusError(
            f"no documents under {root}. Expected {root}/docs, {root}/errors and "
            f"{root}/approved. Check KB_ROOT."
        )
    return docs
