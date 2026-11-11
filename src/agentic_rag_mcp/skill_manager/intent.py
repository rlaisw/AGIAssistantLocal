"""Spec 036 — semantic intent search over the skill store (research R1):
rides the existing Embedder + LanceDB VectorStore; the `skills` collection
holds one document per skill (name join key), re-embedded on every save."""

from __future__ import annotations

from pathlib import Path

from ..store.vectordb import VectorStore

COLLECTION = "skills"


class SkillIntent:
    def __init__(self, vectordb_path: Path, embedder_factory=None):
        """embedder_factory: callable () -> embedder (lazy heavy import);
        tests inject a deterministic double."""
        self._store = VectorStore(Path(vectordb_path))
        self._embedder_factory = embedder_factory
        self._embedder = None

    def _embed(self):
        if self._embedder is None:
            if self._embedder_factory is not None:
                self._embedder = self._embedder_factory()
            else:
                from ..search.embeddings import Embedder  # deferred heavy import

                self._embedder = Embedder()
        return self._embedder

    def upsert(self, name: str, description: str) -> None:
        """Re-embed on save/update — delete+insert, no stale vectors."""
        self._store.upsert_document(
            collection=COLLECTION, document_id=name, title=name,
            text=f"{name}\n{description}", embedder=self._embed())

    def search(self, intent: str, limit: int = 5) -> list[str]:
        """Intent text -> skill names, nearest first."""
        vector = self._embed()([intent])[0]
        return [r["document_id"] for r in
                self._store.search(COLLECTION, vector, limit=limit)]

    def delete(self, name: str) -> None:
        self._store.delete_document(COLLECTION, name)
