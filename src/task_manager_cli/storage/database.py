import sqlite3
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 3


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_item_id TEXT NOT NULL,
            graph_path TEXT,
            file_path TEXT,
            page_name TEXT,
            journal_date TEXT,
            block_uuid TEXT,
            line_start INTEGER,
            line_end INTEGER,
            block_path_json TEXT NOT NULL DEFAULT '[]',
            external_url TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_type, source_item_id)
        );

        CREATE TABLE IF NOT EXISTS source_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_item_id TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            record_type TEXT NOT NULL,
            parent_source_item_id TEXT,
            parent_record_id INTEGER,
            location_id INTEGER,
            observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_created_at TEXT,
            source_updated_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_type, source_item_id),
            FOREIGN KEY(location_id) REFERENCES locations(id)
        );

        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT,
            canonical_source TEXT NOT NULL,
            source_item_id TEXT NOT NULL,
            canonical_location_id INTEGER,
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT,
            created_at_source TEXT NOT NULL DEFAULT 'first_seen_at',
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(canonical_source, source_item_id),
            FOREIGN KEY(canonical_location_id) REFERENCES locations(id)
        );

        CREATE TABLE IF NOT EXISTS object_record_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER NOT NULL,
            record_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(object_id, record_id, role),
            FOREIGN KEY(object_id) REFERENCES objects(id) ON DELETE CASCADE,
            FOREIGN KEY(record_id) REFERENCES source_records(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_object_id INTEGER NOT NULL,
            to_object_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(from_object_id, to_object_id, relation_type),
            FOREIGN KEY(from_object_id) REFERENCES objects(id) ON DELETE CASCADE,
            FOREIGN KEY(to_object_id) REFERENCES objects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_object_id INTEGER,
            target_record_id INTEGER,
            author TEXT NOT NULL,
            annotation_type TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            context_snapshot_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(target_object_id) REFERENCES objects(id) ON DELETE CASCADE,
            FOREIGN KEY(target_record_id) REFERENCES source_records(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            adapter TEXT NOT NULL,
            graph_path TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            dry_run INTEGER NOT NULL DEFAULT 0,
            files_scanned INTEGER NOT NULL DEFAULT 0,
            records_seen INTEGER NOT NULL DEFAULT 0,
            objects_seen INTEGER NOT NULL DEFAULT 0,
            warnings_seen INTEGER NOT NULL DEFAULT 0,
            errors_seen INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS write_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            target_object_id INTEGER,
            target_record_id INTEGER,
            source_type TEXT NOT NULL DEFAULT 'logseq',
            graph_path TEXT,
            file_path TEXT,
            page_name TEXT,
            block_uuid TEXT,
            line_start INTEGER,
            section_marker TEXT,
            content TEXT NOT NULL,
            preview_diff TEXT NOT NULL,
            file_sha256 TEXT,
            backup_path TEXT,
            author TEXT NOT NULL DEFAULT 'agent',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_at TEXT,
            error TEXT,
            FOREIGN KEY(target_object_id) REFERENCES objects(id) ON DELETE SET NULL,
            FOREIGN KEY(target_record_id) REFERENCES source_records(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'suggested',
            risk TEXT NOT NULL DEFAULT 'low',
            target_object_id INTEGER,
            target_record_id INTEGER,
            review_session_id INTEGER,
            source TEXT NOT NULL DEFAULT 'agent',
            rationale TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            applied_record_json TEXT,
            rollback_record_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_at TEXT,
            rejected_at TEXT,
            applied_at TEXT,
            rolled_back_at TEXT,
            FOREIGN KEY(target_object_id) REFERENCES objects(id) ON DELETE SET NULL,
            FOREIGN KEY(target_record_id) REFERENCES source_records(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS proposal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'user',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(proposal_id) REFERENCES proposals(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            title TEXT,
            scope_json TEXT NOT NULL DEFAULT '{}',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS review_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_session_id INTEGER NOT NULL,
            object_id INTEGER,
            record_id INTEGER,
            item_ref TEXT,
            role TEXT NOT NULL DEFAULT 'candidate',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(review_session_id) REFERENCES review_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(object_id) REFERENCES objects(id) ON DELETE SET NULL,
            FOREIGN KEY(record_id) REFERENCES source_records(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_session_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'user',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(review_session_id) REFERENCES review_sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_objects_type ON objects(object_type);
        CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status);
        CREATE INDEX IF NOT EXISTS idx_records_type ON source_records(record_type);
        CREATE INDEX IF NOT EXISTS idx_annotations_target ON annotations(target_object_id, target_record_id);
        CREATE INDEX IF NOT EXISTS idx_write_proposals_status ON write_proposals(status);
        CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
        CREATE INDEX IF NOT EXISTS idx_proposals_review ON proposals(review_session_id);
        CREATE INDEX IF NOT EXISTS idx_review_sessions_status ON review_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_review_items_session ON review_items(review_session_id);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
