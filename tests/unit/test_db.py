"""单测：qmd/core/db.py 新版。"""
from __future__ import annotations

import sqlite3

import pytest

from qmd.core.db import SCHEMA_SQL, open_connection


def test_open_connection_creates_parent_dir(tmp_path):
    db = tmp_path / "nested" / "dir" / "db.sqlite"
    conn = open_connection(db)
    try:
        assert db.exists()
        assert db.parent.is_dir()
    finally:
        conn.close()


def test_schema_tables_created(tmp_path):
    conn = open_connection(tmp_path / "db.sqlite")
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' OR type='virtual table'")
        names = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    for t in ("collections", "documents", "chunks"):
        assert t in names
    assert "chunks_fts" in names
    assert "chunks_vec" in names


def test_foreign_keys_enabled(tmp_path):
    conn = open_connection(tmp_path / "db.sqlite")
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_idempotent_reopen(tmp_path):
    db = tmp_path / "db.sqlite"
    c1 = open_connection(db)
    c1.close()
    c2 = open_connection(db)
    c2.close()


def test_vec_virtual_table_dim_matches_embedder(tmp_path):
    from qmd.core.embedding import Embedder
    conn = open_connection(tmp_path / "db.sqlite")
    try:
        vec = ",".join(["0.0"] * Embedder.DIM)
        conn.execute(f"INSERT INTO chunks_vec(rowid, embedding) VALUES (1, '[{vec}]')")
        conn.commit()
    finally:
        conn.close()


def test_sqlite_version_check(monkeypatch, tmp_path):
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.30.0")
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 30, 0))
    with pytest.raises(RuntimeError, match="3.34"):
        open_connection(tmp_path / "db.sqlite")
