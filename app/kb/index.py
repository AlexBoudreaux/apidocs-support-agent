"""`KnowledgeBase`. Owner is session 4c. Build spec sections 5 and 9.

Two indexes over the same list of `Doc`s.

* **Exact.** Two dicts, `(route, version) -> list[Doc]` and `error_code -> list[Doc]`.
  Both map to a list because `(route, version)` is not unique: `POST /payments`
  and `GET /payments` are two docs on one path, so are `POST` and
  `GET /webhooks/endpoints`, and an approved answer is indexed under the route
  and version it was written against. See the note on method keying below.
* **Semantic.** `InMemoryVectorStore` over each doc's `description`, with a
  callable metadata filter for version, area, and source.

Approved answers live in both indexes tagged `source="approved_answer"`.
`use_cache=False` filters them out of every method, which is how eval runs stop
the answer cache from grading the system on data it memorized.

**Why the exact index is not keyed on HTTP method.** It would disambiguate
create from list, but `SearchQuery` (frozen in `app/state.py`) has no `method`
field, so the planner cannot express the distinction and the key would never be
hit with anything but a guess. Both docs come back and reflect picks, which is
also what build spec section 11 asserts. Recorded in build spec 5.1.

The vector store is built lazily on the first `semantic()` call, not in
`__init__`. Constructing a `KnowledgeBase` therefore costs no network, which
keeps `exact`-only paths (the `fetch_doc_section` tool, `all_doc_ids`, the
loader tests) free of a provider round trip.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from app import settings
from app.kb.loader import load_kb
from app.state import Doc

log = logging.getLogger(__name__)

# "POST /v3/payments/{id}/refund" -> the planner sometimes leads with the verb.
_METHOD = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+", re.IGNORECASE)
# "{id}", "{payment_id}" and ":id" all mean the same path parameter.
_PARAM = re.compile(r"\{[^}]*\}|:[A-Za-z_]\w*")


def _normalize_route(route: str) -> str:
    """Loose form of a route path, for the fallback lookup only.

    Drops an HTTP verb, a query string, the version prefix, and the name inside
    a path parameter, so `POST /v3/payments/{payment_id}/refund?x=1` and
    `/payments/:id/refund` both reduce to `/payments/{id}/refund`. The strict
    key is still tried first, so this never overrides an exact hit.
    """
    return _split_route(route)[1]


def _split_route(route: str) -> tuple[str | None, str]:
    """`(version prefix or None, normalized path)`."""
    text = _METHOD.sub("", route.strip()).split("?")[0].strip().lower()
    text = _PARAM.sub("{id}", text).rstrip("/")
    if not text:
        return None, ""
    if not text.startswith("/"):
        text = "/" + text
    parts = text.split("/")
    if len(parts) > 1 and parts[1] in ("v2", "v3"):
        return parts[1], "/" + "/".join(parts[2:])
    return None, text


class KnowledgeBase:
    """Exact index on `(route, version)` and on `error_code`, plus a semantic index."""

    def __init__(self, docs: list[Doc], embeddings: Embeddings | None = None) -> None:
        self._docs: list[Doc] = []
        self._by_route: dict[tuple[str, str], list[Doc]] = {}
        self._by_norm_route: dict[tuple[str, str], list[Doc]] = {}
        self._by_error_code: dict[str, list[Doc]] = {}

        self._embeddings = embeddings
        self._store: InMemoryVectorStore | None = None
        # The `Send` fan-out runs search branches concurrently, so two threads
        # can reach the lazy build at once. Without this lock one of them sees a
        # store that exists but has not been filled yet and searches nothing.
        self._store_lock = threading.Lock()
        # Docs indexed exactly but not yet embedded. Flushed in one batched
        # embedding call the first time `semantic()` runs, and again after any
        # `add_approved_answer` since the store was last built.
        self._unembedded: list[Doc] = []

        for doc in docs:
            self._add(doc)

    # ---------- construction ----------

    @classmethod
    def load(cls, root: Path = settings.KB_ROOT) -> "KnowledgeBase":
        """Read `docs/`, `errors/` and `approved/` under `root`. Once per process.

        Not a `**/*.md` glob. `kb/CORPUS.md` and `kb/FACTSHEET.md` sit at the
        root, name every route in the corpus, and print the words the corpus is
        deliberately silent on. Loading either poisons retrieval and breaks
        every abstain example. `load_kb` reads the three subdirectories only.
        """
        return cls(load_kb(root))

    def _add(self, doc: Doc) -> None:
        self._docs.append(doc)
        if doc["route"]:
            self._by_route.setdefault((doc["route"], doc["version"]), []).append(doc)
            norm = _normalize_route(doc["route"])
            if norm:
                self._by_norm_route.setdefault((norm, doc["version"]), []).append(doc)
        if doc.get("error_code"):
            self._by_error_code.setdefault(doc["error_code"], []).append(doc)
        self._unembedded.append(doc)

    # ---------- semantic index ----------

    def _ensure_store(self) -> InMemoryVectorStore:
        """Build or top up the vector store, once, under a lock.

        One batched embedding call per flush. Concurrent search branches block
        here on the first call of the process and then never contend again.
        """
        with self._store_lock:
            return self._build_store_locked()

    def _build_store_locked(self) -> InMemoryVectorStore:
        if self._store is None:
            self._embeddings = self._embeddings or settings.embeddings()
            self._store = InMemoryVectorStore(self._embeddings)
        if self._unembedded:
            pending, self._unembedded = self._unembedded, []
            self._store.add_texts(
                texts=[d["description"] for d in pending],
                metadatas=[
                    {
                        "doc_id": d["doc_id"],
                        "source": d["source"],
                        "route": d["route"],
                        "version": d["version"],
                        "area": d["area"],
                        "status": d["status"],
                    }
                    for d in pending
                ],
                # doc_id is the store id, so a hit maps straight back to the Doc
                # and a re-added approved answer replaces rather than duplicates.
                ids=[d["doc_id"] for d in pending],
            )
            log.info("kb: embedded %d description(s)", len(pending))
        return self._store

    # ---------- lookups ----------

    @staticmethod
    def _filter_cache(docs: list[Doc], use_cache: bool) -> list[Doc]:
        if use_cache:
            return list(docs)
        return [d for d in docs if d["source"] != "approved_answer"]

    def exact(self, route: str, version: str, use_cache: bool = True) -> list[Doc]:
        """Every doc on `(route, version)`. The primary index.

        A list, not a doc. Four route paths carry two docs each (create and list
        on `/payments` and on `/webhooks/endpoints`, in both versions), and an
        approved answer shares the key of the doc it was written against.

        `version` is authoritative and this method never crosses versions. A
        route whose own prefix contradicts it (`/v2/...` asked for at `v3`) is a
        conflicting query and returns nothing, so reflect sees a gap and plans
        again rather than the drafter quoting a wrong-version doc. Version
        discipline is the point of the pin, and every eval example that hinges
        on a v2/v3 behavioral difference depends on it.
        """
        hits = self._by_route.get((route, version))
        if hits:
            return self._filter_cache(hits, use_cache)

        prefix, norm = _split_route(route)
        if prefix and prefix != version:
            return []
        return self._filter_cache(self._by_norm_route.get((norm, version), []), use_cache)

    def by_error_code(self, code: str, use_cache: bool = True) -> list[Doc]:
        """Exact hit on an error code, e.g. `PAY_4012`."""
        hits = self._by_error_code.get(code.strip().strip("`").upper(), [])
        return self._filter_cache(hits, use_cache)

    def semantic(
        self,
        text: str,
        version: str | None = None,
        area: str | None = None,
        k: int = 4,
        use_cache: bool = True,
    ) -> list[Doc]:
        """Vector search over `description`, filtered on metadata before top-k.

        A `version` of "v3" also matches docs marked "all", which is how the
        error tables stay reachable from a version-scoped query.
        """
        if not text or not text.strip():
            return []

        by_id = {d["doc_id"]: d for d in self._docs}

        def keep(document) -> bool:
            meta = document.metadata
            if not use_cache and meta["source"] == "approved_answer":
                return False
            if version and meta["version"] not in (version, "all"):
                return False
            if area and area != "unknown" and meta["area"] != area:
                return False
            return True

        store = self._ensure_store()
        hits = store.similarity_search(text, k=k, filter=keep)
        return [by_id[h.id] for h in hits if h.id in by_id]

    # ---------- writes ----------

    def add_approved_answer(self, doc: Doc) -> None:
        """Index one approved answer into both indexes at runtime. post_send calls this.

        The semantic side is deferred to the next `semantic()` call so the write
        path costs nothing when nobody searches afterwards.
        """
        self._add(doc)

    def all_doc_ids(self) -> set[str]:
        """Every doc id currently indexed. The golden set validates against this."""
        return {d["doc_id"] for d in self._docs}
