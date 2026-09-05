"""Transactional SQLite persistence for the standalone supply-chain engine."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock
import time
from typing import Any, Iterator

from preciso_supply_agent.core.models import PreparedPayload, source_ids, stable_id


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    snapshot_effective_date TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'complete', 'failed')),
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    failed_at INTEGER,
    failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    source_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    raw_chunk_id TEXT NOT NULL,
    content TEXT NOT NULL,
    file_path TEXT NOT NULL,
    chunk_order_index INTEGER NOT NULL,
    UNIQUE(document_id, raw_chunk_id)
);
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_evidence (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    source_id TEXT NOT NULL REFERENCES chunks(source_id),
    description TEXT NOT NULL,
    file_path TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    PRIMARY KEY(entity_id, source_id, description, document_id)
);
CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    src_id TEXT NOT NULL REFERENCES entities(entity_id),
    relationship_type TEXT NOT NULL,
    tgt_id TEXT NOT NULL REFERENCES entities(entity_id),
    UNIQUE(src_id, relationship_type, tgt_id)
);
CREATE TABLE IF NOT EXISTS relationship_evidence (
    observation_id TEXT PRIMARY KEY,
    relationship_id TEXT NOT NULL REFERENCES relationships(relationship_id),
    source_id TEXT NOT NULL REFERENCES chunks(source_id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    file_path TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(document_id)
);
CREATE INDEX IF NOT EXISTS idx_relationship_src_type
ON relationships(src_id, relationship_type, tgt_id);
CREATE INDEX IF NOT EXISTS idx_relationship_evidence_relationship
ON relationship_evidence(relationship_id, source_id);
"""


class SnapshotConflict(ValueError):
    pass


class DocumentConflict(ValueError):
    pass


class EntityTypeConflict(ValueError):
    pass


class SupplyChainStore:
    """A small repository whose transactions are the ingestion commit boundary."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ingest(self, payload: PreparedPayload) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            existing_document = connection.execute(
                "SELECT payload_fingerprint, status FROM documents WHERE document_id = ?",
                (payload.document_id,),
            ).fetchone()
            if existing_document:
                if existing_document["payload_fingerprint"] != payload.fingerprint:
                    raise DocumentConflict(
                        f"document `{payload.document_id}` already exists with different content; "
                        "use a new document_id or rebuild the dataset"
                    )
                if existing_document["status"] == "complete":
                    return self._idempotent_result(payload)

            dates = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT snapshot_effective_date FROM documents "
                    "WHERE status = 'complete' AND snapshot_effective_date <> ''"
                )
            }
            if payload.snapshot_effective_date and dates and dates != {payload.snapshot_effective_date}:
                existing = ", ".join(sorted(dates))
                raise SnapshotConflict(
                    f"dataset already contains snapshot date(s) {existing}; cannot mix "
                    f"`{payload.snapshot_effective_date}` without rebuilding the dataset"
                )

            for entity in payload.entities:
                existing = connection.execute(
                    "SELECT entity_type FROM entities WHERE entity_id = ?", (entity["entity_name"],)
                ).fetchone()
                if existing and existing["entity_type"] != entity["entity_type"]:
                    raise EntityTypeConflict(
                        f"entity `{entity['entity_name']}` already has type `{existing['entity_type']}`"
                    )

            now = int(time.time())
            connection.execute(
                "INSERT INTO documents(document_id, file_path, snapshot_effective_date, "
                "payload_fingerprint, status, started_at) VALUES (?, ?, ?, ?, 'pending', ?) "
                "ON CONFLICT(document_id) DO UPDATE SET status='pending', started_at=excluded.started_at, "
                "failed_at=NULL, failure_reason=NULL",
                (
                    payload.document_id,
                    payload.file_path,
                    payload.snapshot_effective_date,
                    payload.fingerprint,
                    now,
                ),
            )

            counts = {
                "chunks": {"added": 0, "skipped_duplicate": 0},
                "entities": {"added": 0, "skipped_duplicate": 0},
                "relationships": {"added": 0, "skipped_duplicate": 0},
            }
            for chunk in payload.chunks:
                source_id = self.namespaced_source_id(payload.document_id, chunk["chunk_id"])
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO chunks(source_id, document_id, raw_chunk_id, content, "
                    "file_path, chunk_order_index) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        source_id,
                        payload.document_id,
                        chunk["chunk_id"],
                        chunk["content"],
                        chunk["file_path"],
                        chunk["chunk_order_index"],
                    ),
                )
                self._count(cursor, counts["chunks"])

            for entity in payload.entities:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO entities(entity_id, entity_type, description) VALUES (?, ?, ?)",
                    (entity["entity_name"], entity["entity_type"], entity["description"]),
                )
                self._count(cursor, counts["entities"])
                for raw_source_id in source_ids(entity["source_id"]):
                    connection.execute(
                        "INSERT OR IGNORE INTO entity_evidence(entity_id, source_id, description, "
                        "file_path, document_id) VALUES (?, ?, ?, ?, ?)",
                        (
                            entity["entity_name"],
                            self.namespaced_source_id(payload.document_id, raw_source_id),
                            entity["description"],
                            entity["file_path"],
                            payload.document_id,
                        ),
                    )

            for relationship in payload.relationships:
                relationship_id = stable_id(
                    "supply-rel-",
                    relationship["src_id"],
                    relationship["relationship_type"],
                    relationship["tgt_id"],
                )
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO relationships(relationship_id, src_id, "
                    "relationship_type, tgt_id) VALUES (?, ?, ?, ?)",
                    (
                        relationship_id,
                        relationship["src_id"],
                        relationship["relationship_type"],
                        relationship["tgt_id"],
                    ),
                )
                self._count(cursor, counts["relationships"])
                for raw_source_id in source_ids(relationship["source_id"]):
                    source_id = self.namespaced_source_id(payload.document_id, raw_source_id)
                    observation_id = stable_id(
                        "supply-evidence-",
                        relationship_id,
                        source_id,
                        relationship["description"],
                        relationship["file_path"],
                        payload.document_id,
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO relationship_evidence(observation_id, relationship_id, "
                        "source_id, description, file_path, document_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            observation_id,
                            relationship_id,
                            source_id,
                            relationship["description"],
                            relationship["file_path"],
                            payload.document_id,
                        ),
                    )

            connection.execute(
                "UPDATE documents SET status='complete', completed_at=? WHERE document_id=?",
                (int(time.time()), payload.document_id),
            )
            return self._success_result(payload, counts)

    def record_failure(self, payload: PreparedPayload, reason: str) -> None:
        with self._lock, self.connect() as connection:
            existing = connection.execute(
                "SELECT status FROM documents WHERE document_id=?", (payload.document_id,)
            ).fetchone()
            if existing and existing["status"] == "complete":
                return
            now = int(time.time())
            connection.execute(
                "INSERT INTO documents(document_id, file_path, snapshot_effective_date, "
                "payload_fingerprint, status, started_at, failed_at, failure_reason) "
                "VALUES (?, ?, ?, ?, 'failed', ?, ?, ?) "
                "ON CONFLICT(document_id) DO UPDATE SET status='failed', failed_at=excluded.failed_at, "
                "failure_reason=excluded.failure_reason",
                (
                    payload.document_id,
                    payload.file_path,
                    payload.snapshot_effective_date,
                    payload.fingerprint,
                    now,
                    now,
                    reason,
                ),
            )

    def status(self) -> dict[str, Any]:
        with self.connect() as connection:
            documents = [dict(row) for row in connection.execute(
                "SELECT document_id, file_path, snapshot_effective_date, status, failure_reason "
                "FROM documents ORDER BY document_id"
            )]
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("chunks", "entities", "relationships", "relationship_evidence")
            }
        incomplete = [item["document_id"] for item in documents if item["status"] != "complete"]
        return {
            "status": "ready" if documents and not incomplete else "not_ready",
            "readiness": bool(documents) and not incomplete,
            "workspace": "supply_chain",
            "snapshot": self.snapshot(documents),
            "documents": documents,
            "counts": counts,
            "ingestion_state": {
                "complete_documents": sum(item["status"] == "complete" for item in documents),
                "incomplete_documents": incomplete,
            },
        }

    def entity(self, entity_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT entity_id, entity_type, description FROM entities WHERE entity_id=?",
                (entity_id,),
            ).fetchone()
            return dict(row) if row else None

    def candidate_paths(self, facility_id: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT m.relationship_id AS m_id, m.src_id AS m_src, m.tgt_id AS component_id, "
                "u.relationship_id AS u_id, u.tgt_id AS product_id "
                "FROM relationships m JOIN relationships u ON u.src_id=m.tgt_id "
                "WHERE m.src_id=? AND m.relationship_type='MANUFACTURES' "
                "AND u.relationship_type='USED_IN' ORDER BY u.tgt_id, m.tgt_id, m.relationship_id, u.relationship_id",
                (facility_id,),
            ).fetchall()
        return [
            (
                {"relationship_id": row["m_id"], "src_id": row["m_src"], "relationship_type": "MANUFACTURES", "tgt_id": row["component_id"]},
                {"relationship_id": row["u_id"], "src_id": row["component_id"], "relationship_type": "USED_IN", "tgt_id": row["product_id"]},
            )
            for row in rows
        ]

    def render_edge(self, edge: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT e.source_id, e.file_path, e.description, c.content "
                "FROM relationship_evidence e LEFT JOIN chunks c ON c.source_id=e.source_id "
                "WHERE e.relationship_id=? ORDER BY e.source_id, e.observation_id",
                (edge["relationship_id"],),
            ).fetchall()
        missing = [row["source_id"] for row in rows if row["content"] is None]
        if not rows:
            missing.append(f"relationship:{edge['relationship_id']}")
        if missing:
            return None, sorted(set(missing))
        return {
            "src_id": edge["src_id"],
            "relationship_type": edge["relationship_type"],
            "tgt_id": edge["tgt_id"],
            "evidence": [
                {
                    "source_id": row["source_id"],
                    "file_path": row["file_path"],
                    "description": row["description"],
                    "chunk": {"chunk_id": row["source_id"], "content": row["content"]},
                }
                for row in rows
            ],
        }, []

    def set_document_status(self, document_id: str, status: str) -> None:
        if status not in {"pending", "complete", "failed"}:
            raise ValueError("invalid document status")
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE documents SET status=? WHERE document_id=?", (status, document_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(document_id)

    def delete_chunk(self, source_id: str) -> None:
        """Integrity-test/repair helper; deleting evidence makes dependent queries fail closed."""
        with self._lock:
            connection = sqlite3.connect(self.database_path)
            try:
                # Deliberately bypass the normal FK invariant to simulate a corrupt
                # evidence store. Production ingestion never performs this operation.
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
                connection.commit()
            finally:
                connection.close()

    @staticmethod
    def namespaced_source_id(document_id: str, raw_chunk_id: str) -> str:
        return f"{document_id}::{raw_chunk_id}"

    @staticmethod
    def snapshot(documents: list[dict[str, Any]]) -> dict[str, Any]:
        complete = [item for item in documents if item["status"] == "complete"]
        return {
            "effective_dates": sorted(
                {item["snapshot_effective_date"] for item in complete if item["snapshot_effective_date"]}
            ),
            "document_ids": sorted(item["document_id"] for item in complete),
        }

    @staticmethod
    def _count(cursor: sqlite3.Cursor, counts: dict[str, int]) -> None:
        counts["added" if cursor.rowcount else "skipped_duplicate"] += 1

    @staticmethod
    def _success_result(payload: PreparedPayload, counts: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "document_id": payload.document_id,
            "message": "Validated supply-chain document committed atomically.",
            "chunks_ingested": len(payload.chunks),
            "entities_merged": len(payload.entities),
            "relationships_merged": len(payload.relationships),
            "ingestion_counts": counts,
            "errors": [],
            "warnings": [],
        }

    @classmethod
    def _idempotent_result(cls, payload: PreparedPayload) -> dict[str, Any]:
        result = cls._success_result(
            payload,
            {
                "chunks": {"added": 0, "skipped_duplicate": len(payload.chunks)},
                "entities": {"added": 0, "skipped_duplicate": len(payload.entities)},
                "relationships": {"added": 0, "skipped_duplicate": len(payload.relationships)},
            },
        )
        result["message"] = "Document already committed; identical ingestion was a no-op."
        return result
