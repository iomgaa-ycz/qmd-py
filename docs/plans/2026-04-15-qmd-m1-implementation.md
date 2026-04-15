# qmd-py M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real `SqliteQmdClient` on SQLite + sqlite-vec + FTS5; pass M0 contract tests parametrized across Fake and Sqlite; pass I1 smoke test; delete all legacy files so every `.py` under `qmd/` is live code.

**Architecture:** Six new files in `qmd/core/` (chunking, retrieval, embedding, db, collection, client) expose the real SQLite-backed implementation of `Collection` and `QmdClient` Protocols defined in `qmd/models.py`. `connect()` switches from returning `FakeQmdClient` to `SqliteQmdClient`. Contract tests fixture is parametrized `[fake, sqlite]` so every invariant runs on both backends. All legacy `qmd/mcp/`, `qmd/llm/`, old `qmd/cli/main.py`, old `qmd/core/*` (chunking/retrieval/db/store/config/document/watcher) and 11 legacy test files are deleted in one commit.

**Tech Stack:** Python 3.11+, SQLite ≥ 3.34 (for trigram tokenizer), `sqlite-vec` (vector virtual table, 1024-dim float32), FTS5 (built-in, BM25 + trigram tokenizer for Chinese), `sentence-transformers` with `Qwen/Qwen3-Embedding-0.6B` (1024-dim), pytest with parametrized fixtures.

**Spec:** `docs/specs/2026-04-15-qmd-m1-design.md`

**Prerequisite reading:** `qmd/models.py` (public Protocol), `qmd/testing/fakes.py` (reference for method semantics), `docs/specs/2026-04-15-qmd-m1-design.md` §3–§7.

**Environment reminder (all shell commands):** prefix with `conda run -n qmd-py` or `source ~/miniconda3/etc/profile.d/conda.sh && conda activate qmd-py &&` per `CLAUDE.md §9`. Examples below use `conda run -n qmd-py` for terseness.

**Spec clarification:** Spec §5.5 lists `update_document`, `list_documents(filters=...)`, `get_chunks` among `SqliteCollection` methods, but these are **not** on the `Collection` Protocol (see `qmd/models.py:54-95`). This plan only implements Protocol methods. `list_documents` returns `list[str]` (IDs). `filters` live on `hybrid_search` only.

**SearchResult shape reminder:** fields are `chunk_ref`, `text`, `score`, `bm25_score`, `vector_score`, `rerank_score`, `metadata`. Spec §7 smoke test used `r.chunk.text` — correct usage is `r.text`. Plan uses correct field names.

---

## Task 0: Create M1 branch and verify environment

**Files:** N/A

- [ ] **Step 1: Create branch from current (post-M0)**

```bash
git checkout -b feat/m1-sqlite-real
```

- [ ] **Step 2: Verify SQLite version ≥ 3.34 (trigram required)**

Run: `conda run -n qmd-py python -c "import sqlite3; print(sqlite3.sqlite_version)"`
Expected: version string `>= 3.34.0`. If lower, halt and report to user — this is a hard blocker.

- [ ] **Step 3: Verify sqlite-vec loads**

Run: `conda run -n qmd-py python -c "import sqlite3, sqlite_vec; c=sqlite3.connect(':memory:'); c.enable_load_extension(True); sqlite_vec.load(c); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Verify sentence-transformers import**

Run: `conda run -n qmd-py python -c "import sentence_transformers; print(sentence_transformers.__version__)"`
Expected: some version string. If not installed: `conda run -n qmd-py pip install sentence-transformers`

- [ ] **Step 5: Confirm M0 contract tests currently green baseline**

Run: `conda run -n qmd-py pytest tests/contract/ -v --no-header -q 2>&1 | tail -10`
Expected: no failures. Capture passing test count for later comparison.

---

## Task 1: `qmd/core/chunking.py` — semantic boundary chunking

**Files:**
- Create: `qmd/core/chunking.py`
- Create: `tests/unit/test_chunking.py`
- Create: `tests/unit/__init__.py` (empty, if not already present)

**Algorithm summary:** Scan `text` for break-point candidates (H1/H2/H3 prefixes, `\n```` fences, `---`/`***` rules, blank lines, newlines) scored by type. Advance a cursor with target jump of `(size - overlap) * 2` chars (heuristic `1 token ≈ 2 chars`). Pick the highest-scoring break point within the `[target - window, target + window]` window, where `window = 2 * size` chars. Apply quadratic distance decay so breaks closer to target score higher. Refuse breaks inside `...` fences. Produce `list[Chunk]` with `char_start < char_end` exact to the original string.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/__init__.py` empty.

Create `tests/unit/test_chunking.py`:

```python
"""单测：qmd/core/chunking.py。"""
from __future__ import annotations

from qmd.core.chunking import Chunk, chunk_document


def test_empty_text_returns_empty_list():
    assert chunk_document("") == []


def test_short_text_returns_single_chunk():
    text = "hello world"
    chunks = chunk_document(text, size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_chunk_preserves_char_indices():
    text = "A\n\n" + ("x" * 600) + "\n\n" + ("y" * 600)
    chunks = chunk_document(text, size=512, overlap=64)
    for c in chunks:
        assert text[c.char_start:c.char_end] == c.text
        assert c.char_start < c.char_end


def test_chunks_are_contiguous_with_overlap():
    text = ("word " * 800).strip()  # ~4000 chars → > 512-token threshold
    chunks = chunk_document(text, size=512, overlap=64)
    assert len(chunks) >= 2
    # 前一 chunk 终点 >= 后一 chunk 起点（有 overlap 或刚好相接）
    for a, b in zip(chunks, chunks[1:]):
        assert a.char_end >= b.char_start


def test_code_fence_not_split_in_middle():
    # 构造：一段长文本中间嵌入代码块，代码块内含目标切分位
    body = "text " * 200  # ~1000 chars
    fenced = "```python\n" + ("code_line\n" * 300) + "```\n"  # ~3200 chars
    text = body + fenced + body
    chunks = chunk_document(text, size=512, overlap=64)
    # 断言：没有任何 chunk 的 char_start 或 char_end 落在代码块内部（不等于 fence 开/闭本身）
    fence_open = text.index("```python")
    fence_close = text.index("```\n", fence_open + 3)
    for c in chunks:
        assert not (fence_open < c.char_start < fence_close), \
            f"chunk start {c.char_start} inside fence [{fence_open},{fence_close}]"


def test_heading_boundary_preferred():
    # 目标切点附近有 H2，应切在 H2 处
    prefix = "a " * 400  # ~800 chars, about target
    text = prefix + "\n## New Section\n" + "b " * 400
    chunks = chunk_document(text, size=512, overlap=64)
    # 找出第一个 chunk 的结束位置附近是否正好是 H2 前
    if len(chunks) >= 2:
        boundary = chunks[0].char_end
        # boundary 应该落在 "## New Section" 之前的空白区域
        section_idx = text.index("## New Section")
        assert abs(boundary - section_idx) <= 50


def test_chunk_is_frozen_dataclass():
    c = Chunk(text="x", char_start=0, char_end=1)
    try:
        c.text = "y"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("Chunk should be frozen")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n qmd-py pytest tests/unit/test_chunking.py -v`
Expected: `ModuleNotFoundError: No module named 'qmd.core.chunking'` or equivalent.

- [ ] **Step 3: Implement `qmd/core/chunking.py`**

```python
"""语义边界分块。

纯函数：无 I/O、无全局状态、无外部依赖。

算法：
1. 扫描 break points：H1/H2/H3 标题、代码块 fence、分隔线、空行、换行，各有基础分。
2. 以字符位置前进，每步目标跳距 = (size - overlap) * 2（启发式 1 token ≈ 2 chars）。
3. 在 [target - window, target + window] 窗口内找最高分 break，应用平方距离衰减。
4. 代码块（``` ... ```）内部绝不切分。
5. 输出 Chunk(text, char_start, char_end)，满足 text == original[char_start:char_end]。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """单个 chunk。char_start 包含、char_end 不包含（Python slice 惯例）。"""
    text: str
    char_start: int
    char_end: int


_CHARS_PER_TOKEN = 2  # 中文保守估算


# 断点模式：(正则, 基础分, 类型标签)。分数越高越偏好。
_BREAK_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\n#{1}(?!#)", re.MULTILINE), 100.0, "h1"),
    (re.compile(r"\n#{2}(?!#)", re.MULTILINE), 90.0, "h2"),
    (re.compile(r"\n#{3}(?!#)", re.MULTILINE), 80.0, "h3"),
    (re.compile(r"\n```", re.MULTILINE), 80.0, "fence"),
    (re.compile(r"\n(?:---|\*\*\*)\s*\n", re.MULTILINE), 60.0, "hr"),
    (re.compile(r"\n\n+", re.MULTILINE), 20.0, "blank"),
    (re.compile(r"\n", re.MULTILINE), 1.0, "newline"),
]

_FENCE_RE = re.compile(r"```", re.MULTILINE)


def _find_fence_ranges(text: str) -> list[tuple[int, int]]:
    """返回所有 ``` ... ``` 区间 [open_start, close_end)。未配对的 fence 视作直到文末。"""
    positions = [m.start() for m in _FENCE_RE.finditer(text)]
    ranges: list[tuple[int, int]] = []
    for i in range(0, len(positions), 2):
        start = positions[i]
        end = positions[i + 1] + 3 if i + 1 < len(positions) else len(text)
        ranges.append((start, end))
    return ranges


def _in_fence(pos: int, ranges: list[tuple[int, int]]) -> bool:
    for a, b in ranges:
        if a < pos < b:
            return True
    return False


def _collect_breaks(text: str, fence_ranges: list[tuple[int, int]]) -> list[tuple[int, float]]:
    """扫描所有候选断点，过滤 fence 内部，返回 (pos, base_score) 升序列表。"""
    breaks: list[tuple[int, float]] = []
    for pattern, base, _kind in _BREAK_PATTERNS:
        for m in pattern.finditer(text):
            pos = m.start()
            if _in_fence(pos, fence_ranges):
                continue
            breaks.append((pos, base))
    breaks.sort(key=lambda x: x[0])
    # 同一位置取最高分
    dedup: dict[int, float] = {}
    for pos, sc in breaks:
        if sc > dedup.get(pos, -1.0):
            dedup[pos] = sc
    return sorted(dedup.items())


def _pick_cutoff(
    breaks: list[tuple[int, float]],
    target: int,
    window: int,
    cursor: int,
    fallback: int,
) -> int:
    """在 [target-window, target+window] 内找最高分断点，带平方距离衰减。都找不到用 fallback。"""
    lo, hi = target - window, target + window
    best_pos = fallback
    best_score = -1.0
    for pos, base in breaks:
        if pos <= cursor:
            continue
        if pos < lo or pos > hi:
            continue
        dist = abs(pos - target) / max(window, 1)
        score = base * (1.0 - dist * dist)
        if score > best_score:
            best_score = score
            best_pos = pos
    return best_pos


def chunk_document(text: str, size: int = 512, overlap: int = 64) -> list[Chunk]:
    """按语义边界切分 markdown。

    参数：
        text: 原始 markdown 字符串。
        size: 目标 chunk 大小（单位：token）。
        overlap: chunk 之间的重叠（单位：token）。

    返回：Chunk 列表，text == original[char_start:char_end]。
    """
    if not text.strip():
        return []

    size_chars = size * _CHARS_PER_TOKEN
    step_chars = max((size - overlap) * _CHARS_PER_TOKEN, 1)
    window_chars = size_chars  # ±size 的窗口

    total = len(text)
    if total <= size_chars:
        return [Chunk(text=text, char_start=0, char_end=total)]

    fence_ranges = _find_fence_ranges(text)
    breaks = _collect_breaks(text, fence_ranges)

    chunks: list[Chunk] = []
    cursor = 0
    while cursor < total:
        target = cursor + size_chars
        if target >= total:
            chunks.append(Chunk(text=text[cursor:total], char_start=cursor, char_end=total))
            break
        cutoff = _pick_cutoff(breaks, target, window_chars, cursor, fallback=target)
        # 保证 cutoff 不在 fence 内部
        if _in_fence(cutoff, fence_ranges):
            cutoff = target
        cutoff = min(max(cutoff, cursor + 1), total)
        chunks.append(Chunk(text=text[cursor:cutoff], char_start=cursor, char_end=cutoff))
        next_cursor = cutoff - overlap * _CHARS_PER_TOKEN
        if next_cursor <= cursor:
            next_cursor = cursor + step_chars
        cursor = min(next_cursor, total)
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n qmd-py pytest tests/unit/test_chunking.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add qmd/core/chunking.py tests/unit/__init__.py tests/unit/test_chunking.py
git commit -m "feat(M1): qmd/core/chunking.py 语义边界分块纯函数"
```

---

## Task 2: `qmd/core/retrieval.py` — Reciprocal Rank Fusion

**Files:**
- Create: `qmd/core/retrieval.py`
- Create: `tests/unit/test_retrieval.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_retrieval.py`:

```python
"""单测：qmd/core/retrieval.py。"""
from qmd.core.retrieval import rrf_fuse


def test_empty_rankings_returns_empty():
    assert rrf_fuse([]) == []


def test_single_ranking_preserves_order():
    result = rrf_fuse([[10, 20, 30]])
    assert [rowid for rowid, _ in result] == [10, 20, 30]
    # 严格降序
    assert all(result[i][1] > result[i + 1][1] for i in range(len(result) - 1))


def test_two_rankings_fuse_both():
    a = [1, 2, 3]
    b = [3, 2, 4]
    result = rrf_fuse([a, b], k=60)
    rowids = [rowid for rowid, _ in result]
    assert set(rowids) == {1, 2, 3, 4}
    # 3 在 a=rank2、b=rank0 都高 → 应 top1
    # 2 在 a=rank1、b=rank1 → top2
    # 1 只在 a=rank0 → 次
    # 4 只在 b=rank2 → 末
    assert rowids[0] == 3


def test_scores_strictly_descending():
    a = [1, 2, 3, 4, 5]
    b = [5, 4, 3, 2, 1]
    result = rrf_fuse([a, b], k=60)
    scores = [s for _, s in result]
    for s1, s2 in zip(scores, scores[1:]):
        assert s1 >= s2  # RRF 允许打平；打平时用 rowid 稳定排序


def test_rrf_formula():
    # 单一 ranking，rrf_score = 1/(k+rank)，rank 从 0 开始
    k = 60
    result = rrf_fuse([[10, 20]], k=k)
    scores = dict(result)
    assert abs(scores[10] - 1 / (k + 0)) < 1e-9
    assert abs(scores[20] - 1 / (k + 1)) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n qmd-py pytest tests/unit/test_retrieval.py -v`
Expected: `ImportError: cannot import name 'rrf_fuse'` or ModuleNotFoundError.

- [ ] **Step 3: Implement `qmd/core/retrieval.py`**

```python
"""Reciprocal Rank Fusion（RRF）纯函数。"""
from __future__ import annotations


def rrf_fuse(
    rankings: list[list[int]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """融合多个排序列表。

    参数：
        rankings: 多个按相关度降序的 rowid 列表。同一 rowid 可能出现在多个列表里。
        k: RRF 常数，默认 60（design §4.1）。

    返回：(rowid, rrf_score) 列表，按 rrf_score 降序；打平时按 rowid 升序（稳定）。
    rrf_score = Σ_i 1 / (k + rank_i(rowid))，rank 从 0 开始。
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, rowid in enumerate(ranking):
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (k + rank)
    # 先按 rowid 升序（tie-breaker），再按 score 降序
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n qmd-py pytest tests/unit/test_retrieval.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add qmd/core/retrieval.py tests/unit/test_retrieval.py
git commit -m "feat(M1): qmd/core/retrieval.py RRF 融合纯函数"
```

---

## Task 3: `qmd/core/embedding.py` — Qwen3-Embedding-0.6B wrapper

**Files:**
- Create: `qmd/core/embedding.py`
- Create: `tests/unit/test_embedding.py`

**Note:** Unit tests mock the model load to avoid downloading 1.2GB per test run. Real model load is exercised in contract tests.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_embedding.py`:

```python
"""单测：qmd/core/embedding.py。不加载真实模型，靠 mock 验证接口。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from qmd.core.embedding import Embedder


def test_embedder_dim_and_model_name_constants():
    assert Embedder.DIM == 1024
    assert Embedder.MODEL_NAME == "Qwen/Qwen3-Embedding-0.6B"


def test_empty_input_returns_empty_list():
    e = Embedder()
    assert e.embed([]) == []


def test_embed_returns_list_of_lists_with_correct_dim():
    e = Embedder()
    fake_model = MagicMock()
    fake_model.encode = MagicMock(
        return_value=np.array([[0.1] * 1024, [0.2] * 1024], dtype=np.float32)
    )
    with patch.object(Embedder, "_load_model", return_value=fake_model):
        result = e.embed(["hello", "world"])
    assert len(result) == 2
    assert all(len(vec) == 1024 for vec in result)
    assert all(isinstance(x, float) for vec in result for x in vec)


def test_model_loaded_lazily_once():
    e = Embedder()
    load_count = [0]

    def fake_load():
        load_count[0] += 1
        m = MagicMock()
        m.encode = MagicMock(return_value=np.zeros((1, 1024), dtype=np.float32))
        return m

    with patch.object(Embedder, "_load_model", side_effect=fake_load):
        e.embed(["a"])
        e.embed(["b"])
        e.embed(["c"])
    assert load_count[0] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n qmd-py pytest tests/unit/test_embedding.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `qmd/core/embedding.py`**

```python
"""Qwen3-Embedding-0.6B 封装（via sentence-transformers）。

- 懒加载：首次 embed 调用时下载/加载模型（~1.2GB，冷启动 5-15s）。
- 批量 encode：默认 batch_size=32。
- 线程安全：_load_model 用锁保护，encode 本身在 ST 内部已线程安全。
"""
from __future__ import annotations

import threading
from typing import Any

from loguru import logger


class Embedder:
    DIM: int = 1024
    MODEL_NAME: str = "Qwen/Qwen3-Embedding-0.6B"

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()

    def _load_model(self) -> Any:
        """首次加载模型。子类或测试可 patch。"""
        from sentence_transformers import SentenceTransformer
        logger.info("正在加载 embedding 模型: {}", self.MODEL_NAME)
        return SentenceTransformer(self.MODEL_NAME)

    def _ensure_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """批量 embed。空 list 直接返回空 list（不触发加载）。"""
        if not texts:
            return []
        model = self._ensure_model()
        vectors = model.encode(texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=False)
        return [[float(x) for x in vec] for vec in vectors]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n qmd-py pytest tests/unit/test_embedding.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add qmd/core/embedding.py tests/unit/test_embedding.py
git commit -m "feat(M1): qmd/core/embedding.py Qwen3-Embedding-0.6B 封装"
```

---

## Task 4: `qmd/core/db.py` — connection + schema init

**Files:**
- Create: `qmd/core/db.py`
- Create: `tests/unit/test_db.py` (replaces any existing old test_db.py — but we keep old one for now, delete in cleanup Task 9)

**Note:** The existing `tests/test_db.py` tests the legacy `qmd.core.db` module; since we are about to overwrite `qmd/core/db.py`, the legacy test will break. That's acceptable — it's on the delete list in Task 9. In the meantime we create `tests/unit/test_db.py` for the new module. When the legacy test breaks, run `pytest` excluding it: `pytest --ignore=tests/test_db.py`.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_db.py`:

```python
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
    # 必需的 4 张常规表
    for t in ("collections", "documents", "chunks"):
        assert t in names
    # FTS5 + vec0 虚表会在 sqlite_master 里以主名出现
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
    c2 = open_connection(db)  # 不应报错
    c2.close()


def test_vec_virtual_table_dim_matches_embedder(tmp_path):
    from qmd.core.embedding import Embedder
    conn = open_connection(tmp_path / "db.sqlite")
    try:
        # 插入一个 DIM 维向量应成功
        vec = ",".join(["0.0"] * Embedder.DIM)
        conn.execute(f"INSERT INTO chunks_vec(rowid, embedding) VALUES (1, '[{vec}]')")
        conn.commit()
    finally:
        conn.close()


def test_sqlite_version_check(monkeypatch, tmp_path):
    # 模拟低版本 SQLite，应抛 RuntimeError
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.30.0")
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 30, 0))
    with pytest.raises(RuntimeError, match="3.34"):
        open_connection(tmp_path / "db.sqlite")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n qmd-py pytest tests/unit/test_db.py -v`
Expected: ImportError (SCHEMA_SQL / open_connection not found).

- [ ] **Step 3: Implement `qmd/core/db.py`**

```python
"""SQLite 连接管理 + schema 初始化。

- 启动时检查 SQLite >= 3.34（FTS5 trigram tokenizer 需要）。
- 加载 sqlite-vec 扩展。
- 执行幂等 schema。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from qmd.core.embedding import Embedder


_MIN_SQLITE = (3, 34, 0)


SCHEMA_SQL: str = f"""
CREATE TABLE IF NOT EXISTS collections (
    name       TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    collection  TEXT NOT NULL,
    id          TEXT NOT NULL,
    markdown    TEXT NOT NULL,
    metadata    TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (collection, id),
    FOREIGN KEY (collection) REFERENCES collections(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    collection  TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    char_start  INTEGER NOT NULL,
    char_end    INTEGER NOT NULL,
    FOREIGN KEY (collection, document_id)
        REFERENCES documents(collection, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(collection, document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding FLOAT[{Embedder.DIM}]
);
"""


def _check_sqlite_version() -> None:
    if sqlite3.sqlite_version_info < _MIN_SQLITE:
        raise RuntimeError(
            f"qmd 需要 SQLite >= 3.34（FTS5 trigram 分词器），"
            f"当前版本 {sqlite3.sqlite_version}"
        )


def open_connection(db_path: str | Path) -> sqlite3.Connection:
    """打开连接、加载 sqlite-vec、执行 schema。幂等。"""
    _check_sqlite_version()
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n qmd-py pytest tests/unit/test_db.py -v --ignore=tests/test_db.py`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add qmd/core/db.py tests/unit/test_db.py
git commit -m "feat(M1): qmd/core/db.py 新 schema + sqlite-vec 初始化"
```

---

## Task 5: `qmd/core/collection.py` — SqliteCollection

**Files:**
- Create: `qmd/core/collection.py`
- Create: `tests/unit/test_collection.py`

**Note:** This task's tests exercise a real SQLite connection + the real Embedder. Tests will download the Qwen3 model on first run (~1.2GB, 5-15s). This is acceptable because contract tests will do it anyway. Use `@pytest.fixture(scope="module")` to share the client across tests in this file.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_collection.py`:

```python
"""单测：qmd/core/collection.py（依赖真实 Embedder）。

首次运行会下载 Qwen3-Embedding-0.6B (~1.2GB)。
"""
from __future__ import annotations

import pytest

from qmd.core.client import SqliteQmdClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("col") / "db.sqlite"
    c = SqliteQmdClient(db)
    yield c
    c.close()


@pytest.fixture
def col(client):
    name = f"test_{id(object())}"
    c = client.collection(name)
    yield c
    client.delete_collection(name)


def test_add_and_get_document(col):
    col.add_document("d1", "# Hello\n\nworld", metadata={"tag": "a"})
    doc = col.get_document("d1")
    assert doc is not None
    assert doc["id"] == "d1"
    assert doc["markdown"] == "# Hello\n\nworld"
    assert doc["metadata"] == {"tag": "a"}
    assert doc["chunk_count"] >= 1


def test_add_document_is_upsert(col):
    col.add_document("d1", "first version")
    col.add_document("d1", "second version")
    doc = col.get_document("d1")
    assert doc["markdown"] == "second version"


def test_delete_document(col):
    col.add_document("d1", "to be deleted")
    col.delete_document("d1")
    assert col.get_document("d1") is None


def test_delete_nonexistent_is_noop(col):
    col.delete_document("never_existed")  # 不应抛


def test_list_documents(col):
    col.add_document("a", "content a")
    col.add_document("b", "content b")
    ids = col.list_documents()
    assert set(ids) == {"a", "b"}


def test_info_counts(col):
    col.add_document("x", "# Title\n\nbody text")
    info = col.info()
    assert info.name == col.name
    assert info.document_count == 1
    assert info.chunk_count >= 1
    assert info.embedding_dim == 1024


def test_hybrid_search_returns_results(col):
    col.add_document("d1", "The quick brown fox jumps over the lazy dog.")
    col.add_document("d2", "Python is a programming language.")
    results = col.hybrid_search("programming language", top_k=5)
    assert len(results) >= 1
    # Python 文档应排前
    assert results[0].chunk_ref.document_id == "d2"
    # 结果按 score 严格降序
    for a, b in zip(results, results[1:]):
        assert a.score >= b.score


def test_hybrid_search_rerank_is_noop_in_m1(col):
    col.add_document("d1", "hello world")
    results_a = col.hybrid_search("hello", rerank=False)
    results_b = col.hybrid_search("hello", rerank=True)
    # rerank 参数 M1 no-op：返回同样的 score 排序，rerank_score 恒为 None
    assert [r.chunk_ref.document_id for r in results_a] == [r.chunk_ref.document_id for r in results_b]
    assert all(r.rerank_score is None for r in results_b)


def test_char_indices_match_original(col):
    md = "# H\n\n" + "x" * 1500 + "\n\n## H2\n\n" + "y" * 1500
    col.add_document("d", md)
    doc = col.get_document("d")
    assert doc is not None
    # 每个 chunk 的 text 必须 == markdown[char_start:char_end]
    results = col.hybrid_search("x", top_k=10)
    for r in results:
        assert md[r.chunk_ref.char_start:r.chunk_ref.char_end] == r.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n qmd-py pytest tests/unit/test_collection.py -v --ignore=tests/test_db.py`
Expected: ImportError (SqliteQmdClient not found — we haven't written client.py yet).

- [ ] **Step 3: Implement `qmd/core/collection.py`**

```python
"""SqliteCollection — 真实 SQLite 后端的 Collection Protocol 实现。

线程安全：所有方法包在单一 threading.Lock 里。
事务：add_document 在单一 BEGIN/COMMIT 内完成 delete-old + upsert-doc + insert-chunks。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from qmd.core.chunking import chunk_document
from qmd.core.embedding import Embedder
from qmd.core.retrieval import rrf_fuse
from qmd.models import ChunkRef, CollectionInfo, SearchResult


# 硬编码常量（M2 迁 qmd.yaml）
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
RRF_K = 60
BM25_TOP_K = 20
VECTOR_TOP_K = 20
EMBEDDING_BATCH_SIZE = 32


def _vec_to_sqlite_literal(vec: list[float]) -> str:
    """sqlite-vec 的 MATCH 接受 JSON array 字符串。"""
    return json.dumps(vec)


class SqliteCollection:
    """实现 qmd.models.Collection Protocol。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        name: str,
        lock: threading.Lock,
        embedder: Embedder,
    ) -> None:
        self.name = name
        self._conn = conn
        self._lock = lock
        self._embedder = embedder

    # --- mutations ---

    def add_document(
        self,
        document_id: str,
        markdown: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        now = int(time.time() * 1000)
        chunks = chunk_document(markdown, size=CHUNK_SIZE_TOKENS, overlap=CHUNK_OVERLAP_TOKENS)

        embeddings: list[list[float]] = []
        if chunks:
            embeddings = self._embedder.embed(
                [c.text for c in chunks], batch_size=EMBEDDING_BATCH_SIZE
            )

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                self._delete_chunks_locked(cur, document_id)
                cur.execute(
                    """
                    INSERT INTO documents(collection, id, markdown, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(collection, id) DO UPDATE SET
                        markdown=excluded.markdown,
                        metadata=excluded.metadata,
                        updated_at=excluded.updated_at
                    """,
                    (self.name, document_id, markdown, meta_json, now, now),
                )
                for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    cur.execute(
                        """
                        INSERT INTO chunks(collection, document_id, chunk_index, text, char_start, char_end)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (self.name, document_id, idx, chunk.text, chunk.char_start, chunk.char_end),
                    )
                    rowid = cur.lastrowid
                    cur.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (rowid, chunk.text))
                    cur.execute(
                        "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                        (rowid, _vec_to_sqlite_literal(emb)),
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                self._delete_chunks_locked(cur, document_id)
                cur.execute(
                    "DELETE FROM documents WHERE collection=? AND id=?",
                    (self.name, document_id),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _delete_chunks_locked(self, cur: sqlite3.Cursor, document_id: str) -> None:
        """删除该文档的所有 chunks（含 fts/vec 影子）。调用者须持锁 + 在事务内。"""
        rows = cur.execute(
            "SELECT rowid FROM chunks WHERE collection=? AND document_id=?",
            (self.name, document_id),
        ).fetchall()
        rowids = [r[0] for r in rows]
        for rowid in rowids:
            cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
            cur.execute("DELETE FROM chunks_vec WHERE rowid=?", (rowid,))
        cur.execute(
            "DELETE FROM chunks WHERE collection=? AND document_id=?",
            (self.name, document_id),
        )

    # --- reads ---

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT markdown, metadata FROM documents WHERE collection=? AND id=?",
                (self.name, document_id),
            ).fetchone()
            if row is None:
                return None
            markdown, meta_json = row
            chunk_count = self._conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE collection=? AND document_id=?",
                (self.name, document_id),
            ).fetchone()[0]
            return {
                "id": document_id,
                "markdown": markdown,
                "metadata": json.loads(meta_json),
                "chunk_count": chunk_count,
            }

    def list_documents(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM documents WHERE collection=? ORDER BY id",
                (self.name,),
            ).fetchall()
            return [r[0] for r in rows]

    def info(self) -> CollectionInfo:
        with self._lock:
            doc_count = self._conn.execute(
                "SELECT COUNT(*) FROM documents WHERE collection=?", (self.name,)
            ).fetchone()[0]
            chunk_count = self._conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE collection=?", (self.name,)
            ).fetchone()[0]
            return CollectionInfo(
                name=self.name,
                document_count=doc_count,
                chunk_count=chunk_count,
                embedding_dim=Embedder.DIM if chunk_count else None,
            )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,  # M1 no-op
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if not query.strip() or top_k <= 0:
            return []
        query_vec = self._embedder.embed([query])[0]
        with self._lock:
            filter_sql, filter_params = self._build_filter_clause(filters)

            bm25_sql = f"""
                SELECT c.rowid FROM chunks_fts f
                JOIN chunks c ON c.rowid = f.rowid
                JOIN documents d ON d.collection = c.collection AND d.id = c.document_id
                WHERE c.collection = ? AND f.text MATCH ?{filter_sql}
                ORDER BY rank LIMIT ?
            """
            bm25_rows = self._conn.execute(
                bm25_sql,
                (self.name, query, *filter_params, BM25_TOP_K),
            ).fetchall()
            bm25_ids = [r[0] for r in bm25_rows]

            vec_sql = f"""
                SELECT c.rowid FROM chunks_vec v
                JOIN chunks c ON c.rowid = v.rowid
                JOIN documents d ON d.collection = c.collection AND d.id = c.document_id
                WHERE c.collection = ? AND v.embedding MATCH ? AND k = ?{filter_sql}
                ORDER BY distance
            """
            vec_rows = self._conn.execute(
                vec_sql,
                (self.name, _vec_to_sqlite_literal(query_vec), VECTOR_TOP_K, *filter_params),
            ).fetchall()
            vec_ids = [r[0] for r in vec_rows]

            fused = rrf_fuse([bm25_ids, vec_ids], k=RRF_K)[:top_k]
            if not fused:
                return []

            rowid_to_score = dict(fused)
            placeholders = ",".join("?" for _ in fused)
            detail_rows = self._conn.execute(
                f"""
                SELECT c.rowid, c.document_id, c.chunk_index, c.text, c.char_start, c.char_end, d.metadata
                FROM chunks c
                JOIN documents d ON d.collection = c.collection AND d.id = c.document_id
                WHERE c.rowid IN ({placeholders})
                """,
                tuple(rowid for rowid, _ in fused),
            ).fetchall()

            results: list[SearchResult] = []
            for rowid, doc_id, chunk_idx, text, cs, ce, meta_json in detail_rows:
                results.append(
                    SearchResult(
                        chunk_ref=ChunkRef(
                            document_id=doc_id, chunk_index=chunk_idx,
                            char_start=cs, char_end=ce,
                        ),
                        text=text,
                        score=rowid_to_score[rowid],
                        bm25_score=None,
                        vector_score=None,
                        rerank_score=None,
                        metadata=json.loads(meta_json),
                    )
                )
            results.sort(key=lambda r: -r.score)
            return results

    def _build_filter_clause(self, filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
        """把 filters dict 转成 WHERE 片段。MVP 仅支持精确相等。"""
        if not filters:
            return "", []
        parts: list[str] = []
        params: list[Any] = []
        for key, val in filters.items():
            parts.append(f" AND json_extract(d.metadata, ?) = ?")
            params.append(f"$.{key}")
            params.append(val)
        return "".join(parts), params
```

- [ ] **Step 4: Skip this step** (tests will run in Task 6 once SqliteQmdClient exists — SqliteCollection needs the client to wire up)

- [ ] **Step 5: Commit**

```bash
git add qmd/core/collection.py tests/unit/test_collection.py
git commit -m "feat(M1): qmd/core/collection.py SqliteCollection 实现"
```

---

## Task 6: `qmd/core/client.py` + switch `connect()` + parametrize contract tests

**Files:**
- Create: `qmd/core/client.py`
- Modify: `qmd/models.py` (connect function body)
- Modify: `tests/contract/conftest.py` (parametrize qmd_client_factory)

- [ ] **Step 1: Implement `qmd/core/client.py`**

```python
"""SqliteQmdClient — 真实 SQLite 后端的 QmdClient Protocol 实现。"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from qmd.core.collection import SqliteCollection
from qmd.core.db import open_connection
from qmd.core.embedding import Embedder
from qmd.models import CollectionInfo


class SqliteQmdClient:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection = open_connection(self._db_path)
        self._lock = threading.Lock()
        self._embedder = Embedder()
        self._collections: dict[str, SqliteCollection] = {}

    def collection(self, name: str) -> SqliteCollection:
        with self._lock:
            if name not in self._collections:
                self._conn.execute(
                    "INSERT OR IGNORE INTO collections(name, created_at) VALUES (?, ?)",
                    (name, int(time.time() * 1000)),
                )
                self._conn.commit()
                self._collections[name] = SqliteCollection(
                    conn=self._conn, name=name, lock=self._lock, embedder=self._embedder,
                )
            return self._collections[name]

    def list_collections(self) -> list[CollectionInfo]:
        with self._lock:
            names = [r[0] for r in self._conn.execute(
                "SELECT name FROM collections ORDER BY name"
            ).fetchall()]
        return [self.collection(n).info() for n in names]

    def delete_collection(self, name: str) -> None:
        with self._lock:
            rowids = [r[0] for r in self._conn.execute(
                "SELECT rowid FROM chunks WHERE collection=?", (name,)
            ).fetchall()]
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                for rowid in rowids:
                    cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
                    cur.execute("DELETE FROM chunks_vec WHERE rowid=?", (rowid,))
                # collections 级联到 documents，documents 级联到 chunks
                cur.execute("DELETE FROM collections WHERE name=?", (name,))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            self._collections.pop(name, None)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
            self._collections.clear()
```

- [ ] **Step 2: Modify `qmd/models.py::connect` to return SqliteQmdClient**

Replace the body of `connect` in `qmd/models.py` (lines 119-130):

```python
def connect(db_path: str | Path | None = None) -> QmdClient:
    """工厂函数：创建一个 SqliteQmdClient 实例。

    db_path 解析顺序：参数 > 环境变量 QMD_DB_PATH > ~/.qmd/db.sqlite。
    首次连接自动创建父目录 + schema。
    """
    import os

    from qmd.core.client import SqliteQmdClient

    if db_path is None:
        env = os.environ.get("QMD_DB_PATH")
        db_path = Path(env) if env else Path.home() / ".qmd" / "db.sqlite"
    return SqliteQmdClient(Path(db_path))
```

- [ ] **Step 3: Parametrize `tests/contract/conftest.py`**

Read current `tests/contract/conftest.py` first, then modify the `qmd_client_factory` fixture. The current content (M0 version):

```python
# 旧的非参数化版本 — 将被替换
@pytest.fixture
def qmd_client_factory():
    from qmd.testing import FakeQmdClient
    return lambda: FakeQmdClient()
```

Replace with:

```python
@pytest.fixture(params=["fake", "sqlite"])
def qmd_client_factory(request, tmp_path):
    """参数化：每个契约测试在 [fake] 和 [sqlite] 各跑一遍。"""
    backend = request.param
    if backend == "fake":
        from qmd.testing import FakeQmdClient
        def factory():
            return FakeQmdClient()
    else:
        from qmd.core.client import SqliteQmdClient
        def factory():
            return SqliteQmdClient(tmp_path / "contract.sqlite")
    yield factory
```

Keep the `qmd_client` fixture unchanged (it consumes `qmd_client_factory` and calls `close()`).

- [ ] **Step 4: Run Task 5's unit tests (now viable)**

Run: `conda run -n qmd-py pytest tests/unit/test_collection.py -v --ignore=tests/test_db.py`
Expected: all 8 tests PASS. First run downloads Qwen3 model (~1.2GB, 5-15s).

- [ ] **Step 5: Run contract tests on parametrized fixture**

Run: `conda run -n qmd-py pytest tests/contract/ -v --ignore=tests/test_db.py 2>&1 | tail -30`
Expected: each test case appears twice — once with `[fake]` suffix, once with `[sqlite]`. All pass.

If some contract tests fail on `[sqlite]`, inspect the failure and adjust `SqliteCollection` / `SqliteQmdClient` implementation. Common gotchas:
- BM25 MATCH query syntax: trigram tokenizer wants raw query; no special escaping needed for plain words
- Vector MATCH: `sqlite-vec` requires `k = ?` in WHERE; see `vec_sql` in collection.py
- `list_collections` for empty DB must return `[]`, not fail

- [ ] **Step 6: Commit**

```bash
git add qmd/core/client.py qmd/models.py tests/contract/conftest.py
git commit -m "feat(M1): SqliteQmdClient + connect() 切换 + 契约测试参数化"
```

---

## Task 7: Smoke test (I1)

**Files:**
- Create: `tests/contract/test_smoke.py`

- [ ] **Step 1: Write the smoke test**

```python
"""I1 smoke test：真实 fixture 跑完整 add + search 流程。"""
from __future__ import annotations


def test_smoke_guide_excerpt(qmd_client, guide_excerpt_markdown):
    col = qmd_client.collection("smoke")
    col.add_document("guide", guide_excerpt_markdown)
    results = col.hybrid_search("Collection 隔离", top_k=3)
    assert len(results) >= 1, "期望至少召回一条结果"
    # fixture 的第一章节讲 Collection，top-1 应该命中
    assert any(
        "Collection" in r.text or "collection" in r.text.lower()
        for r in results
    ), f"期望 top_k 结果中至少一条提及 Collection，实际: {[r.text[:60] for r in results]}"
```

- [ ] **Step 2: Run the smoke test**

Run: `conda run -n qmd-py pytest tests/contract/test_smoke.py -v`
Expected: 2 passes (`test_smoke_guide_excerpt[fake]` and `[sqlite]`).

- [ ] **Step 3: Commit**

```bash
git add tests/contract/test_smoke.py
git commit -m "test(M1): I1 smoke test（真实 fixture add + hybrid_search）"
```

---

## Task 8: Upgrade `FakeQmdClient` embedder to Qwen3

**Files:**
- Modify: `qmd/testing/fakes.py`

**Why:** Spec decision #2 — Fake and Sqlite both use Qwen3-Embedding-0.6B for consistency. Current Fake uses `all-MiniLM-L6-v2` (384-dim).

- [ ] **Step 1: Modify `qmd/testing/fakes.py`**

Change the constant and model string. Find and replace:

```python
# old
_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2
```

to:

```python
# new
_EMBEDDING_DIM = 1024  # Qwen3-Embedding-0.6B
```

Then find `_EmbedderHolder` (near the bottom) and update the model name it loads. Look for the `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` call and replace with `SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")`.

Exact old snippet (grep for it first to confirm): run `grep -n "all-MiniLM" qmd/testing/fakes.py`. Replace the model string with `"Qwen/Qwen3-Embedding-0.6B"`.

- [ ] **Step 2: Run Fake-specific contract tests**

Run: `conda run -n qmd-py pytest tests/contract/ -v -k "fake" 2>&1 | tail -20`
Expected: all `[fake]` contract tests still pass (now with 1024-dim embeddings).

- [ ] **Step 3: Run full contract suite**

Run: `conda run -n qmd-py pytest tests/contract/ -v 2>&1 | tail -15`
Expected: all tests pass on both backends.

- [ ] **Step 4: Commit**

```bash
git add qmd/testing/fakes.py
git commit -m "refactor(M1): Fake 升级到 Qwen3-Embedding-0.6B（1024 维）"
```

---

## Task 9: Legacy cleanup — delete all dead files in one commit

**Files to DELETE:**

Python source:
- `qmd/mcp/` (entire directory)
- `qmd/llm/` (entire directory)
- `qmd/cli/main.py` `qmd/cli/search.py` `qmd/cli/embed.py` `qmd/cli/collection.py` `qmd/cli/context.py` `qmd/cli/formatter.py`
- `qmd/core/store.py` `qmd/core/config.py` `qmd/core/document.py` `qmd/core/watcher.py`
- Any `qmd/utils/*` file that has no active importer (check below)

Tests:
- `tests/test_chunking.py` `tests/test_cli.py` `tests/test_config.py` `tests/test_db.py` `tests/test_document.py` `tests/test_e2e.py` `tests/test_formatter.py` `tests/test_llm.py` `tests/test_llm_base.py` `tests/test_llm_flagembed.py` `tests/test_llm_llama_cpp.py` `tests/test_llm_models.py` `tests/test_llm_sentence_tf.py` `tests/test_retrieval.py` `tests/test_store.py` `tests/test_watcher.py`

**Files to MODIFY:**
- `pyproject.toml` — remove `watchdog` from deps; remove `mvp` and `mcp` optional groups; promote `sentence-transformers`, `numpy` to main deps.

- [ ] **Step 1: Verify `qmd/utils/` usage**

Run: `conda run -n qmd-py python -c "import qmd; import qmd.cli.__main__; import qmd.core.client; import qmd.testing.fakes; import qmd.testing.contract; print('ok')"`
Expected: `ok`. Then:
Run: `grep -rn "from qmd.utils\|import qmd.utils" qmd/ tests/contract/ tests/unit/ 2>&1`
- If any file in this output is NOT on the delete list → that util file must be kept.
- If only legacy (to-be-deleted) files reference utils → delete the unreferenced util files too.

List utils files kept vs deleted on the commit message.

- [ ] **Step 2: Delete Python source directories and files**

```bash
rm -rf qmd/mcp/ qmd/llm/
rm qmd/cli/main.py qmd/cli/search.py qmd/cli/embed.py qmd/cli/collection.py qmd/cli/context.py qmd/cli/formatter.py
rm qmd/core/store.py qmd/core/config.py qmd/core/document.py qmd/core/watcher.py
# legacy core files (superseded by new versions)
# chunking.py / retrieval.py / db.py were OVERWRITTEN in Tasks 1/2/4 — no delete needed.
# Delete any unreferenced qmd/utils/*.py found in Step 1.
```

- [ ] **Step 3: Delete legacy test files**

```bash
rm tests/test_chunking.py tests/test_cli.py tests/test_config.py tests/test_db.py tests/test_document.py
rm tests/test_e2e.py tests/test_formatter.py tests/test_llm.py tests/test_llm_base.py
rm tests/test_llm_flagembed.py tests/test_llm_llama_cpp.py tests/test_llm_models.py tests/test_llm_sentence_tf.py
rm tests/test_retrieval.py tests/test_store.py tests/test_watcher.py
```

Also check for orphan test utilities:
Run: `ls tests/ | grep -v "^contract$\|^fixtures$\|^unit$\|^__init__\|^conftest"`
- Any remaining files that test deleted modules → delete.

- [ ] **Step 4: Update `pyproject.toml`**

Modify the `[project]` → `dependencies` block to:

```toml
dependencies = [
    "sqlite-vec",
    "pydantic",
    "loguru",
    "sentence-transformers",
    "numpy",
]
```

(Removed: `PyYAML` — we'll re-add in M2 when yaml config lands; `watchdog` — only used by deleted watcher.)

Remove `[project.optional-dependencies].mvp` block entirely.
Remove `[project.optional-dependencies].mcp` block entirely.

Keep `dev`, `testing` groups.

In `testing` group, REMOVE `sentence-transformers` and `numpy` (now in main) but keep `rank-bm25` (Fake-only dep):

```toml
testing = [
    "pytest",
    "pytest-asyncio",
    "rank-bm25",
    "deepdiff",
]
```

- [ ] **Step 5: Sync pyproject and verify imports still work**

Run: `conda run -n qmd-py pip install -e . --quiet 2>&1 | tail -5`
Expected: install succeeds.
Run: `conda run -n qmd-py python -c "from qmd import connect, ChunkRef, SearchResult, CollectionInfo, Collection, QmdClient; print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Run full test suite to confirm no regressions**

Run: `conda run -n qmd-py pytest tests/ -v 2>&1 | tail -30`
Expected: only `tests/contract/` and `tests/unit/` collected; all pass.

- [ ] **Step 7: Dead symbol scan (DoD check)**

Run: `grep -rnE "create_store|NamedCollection|BackendType|LLMBackend|create_llm_backend" qmd/ 2>&1`
Expected: **zero results** (except possibly spec/plan docs, not source). If any found: inspect and fix (these should be gone).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(M1): 清理旧代码（删除 mcp/ llm/ 旧 cli/ 旧 core/ + 11 个旧测试）"
```

---

## Task 10: Update `CLAUDE.md` §5.3 chunking params

**Files:**
- Modify: `CLAUDE.md` §5.3

- [ ] **Step 1: Read current `CLAUDE.md` §5.3**

Locate the section with `### 5.3 智能 Chunking` and current params `900 tokens/chunk, 重叠 15% (135 tokens), 搜索窗口 200 tokens`.

- [ ] **Step 2: Replace params**

Find and replace (use Edit tool with exact old/new strings):

Old:
```
**参数**:
- **目标大小**: 900 tokens/chunk
- **重叠**: 15% (135 tokens)
- **搜索窗口**: 200 tokens
```

New:
```
**参数** (M1 对齐 Qwen3-Embedding-0.6B 的 max_seq_length=512):
- **目标大小**: 512 tokens/chunk
- **重叠**: 64 tokens (~12%)
- **搜索窗口**: ±size 字符数
- **Token 估算**: `len(text) // 2`（启发式，中文保守；M2 换精确 Qwen3 tokenizer）
```

Also find `tokens * 2` (CLAUDE.md §5.3 "中文 token 估算") and confirm note is consistent; add `(启发式，M2 替换为精确 tokenizer)` if not already clear.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(M1): CLAUDE.md §5.3 chunking 参数同步到 512/64"
```

---

## Task 11: Final DoD verification

- [ ] **Step 1: Run full contract suite**

Run: `conda run -n qmd-py pytest tests/contract/ -v 2>&1 | tail -20`
Expected: all tests pass on `[fake]` and `[sqlite]`. Total count ≈ M0 count × 2 + 2 (smoke × 2).

- [ ] **Step 2: Run unit suite**

Run: `conda run -n qmd-py pytest tests/unit/ -v 2>&1 | tail -15`
Expected: all chunking/retrieval/embedding/db/collection tests pass.

- [ ] **Step 3: Directory shape check**

Run:
```bash
ls qmd/core/ && echo "---" && ls qmd/ && echo "---" && ls qmd/cli/
```
Expected:
- `qmd/core/` = `__init__.py chunking.py client.py collection.py db.py embedding.py retrieval.py`
- `qmd/` has NO `mcp/` or `llm/` directory
- `qmd/cli/` = `__init__.py __main__.py`

- [ ] **Step 4: Dead symbol grep**

Run: `grep -rnE "create_store|NamedCollection|BackendType|LLMBackend|create_llm_backend" qmd/ 2>&1`
Expected: zero results.

- [ ] **Step 5: CLI smoke**

Run:
```bash
conda run -n qmd-py python -c "
from qmd import connect
from pathlib import Path
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    c = connect(Path(d) / 'test.sqlite')
    col = c.collection('demo')
    with open('tests/fixtures/guide_excerpt.md') as f:
        col.add_document('d1', f.read())
    res = col.hybrid_search('Collection', top_k=3)
    print('hits:', len(res), 'top text:', res[0].text[:60])
    c.close()
"
```
Expected: `hits: >=1`, top text snippet printed.

- [ ] **Step 6: CLI binary smoke**

Run:
```bash
export QMD_DB_PATH=/tmp/qmd_m1_smoke.sqlite
conda run -n qmd-py qmd collection list
conda run -n qmd-py qmd document add --collection demo --document-id d1 --markdown-file tests/fixtures/guide_excerpt.md
conda run -n qmd-py qmd search --collection demo --query "Collection 隔离" --top-k 3
rm /tmp/qmd_m1_smoke.sqlite
```
Expected: each command prints JSON to stdout, exit 0.

- [ ] **Step 7: Tag M1 completion**

```bash
git tag m1-sqlite-real
```

- [ ] **Step 8: Print summary**

Print list of all commits from Task 0 to now with `git log m0-contract-freeze..HEAD --oneline` for the report.

---

## Summary Checklist (from spec §9)

- [ ] `pytest tests/contract/ -v` all green (~188 parametrized test cases)
- [ ] `ls qmd/core/` = `__init__.py chunking.py client.py collection.py db.py embedding.py retrieval.py`
- [ ] `ls qmd/` has no `mcp/`, no `llm/`
- [ ] `ls qmd/cli/` = `__init__.py __main__.py`
- [ ] `grep -nE "create_store|NamedCollection|BackendType|LLMBackend|create_llm_backend" qmd/` empty
- [ ] `test_smoke_guide_excerpt[fake]` and `[sqlite]` both green
- [ ] CLI commands (`qmd collection list`, `qmd document add/list/get/delete`, `qmd search`) work against real SQLite
- [ ] `CLAUDE.md §5.3` updated to 512/64
- [ ] Spec explicitly records M2 deferred items (qmd.yaml, llama_cpp, rerank, batch API, precise tokenizer)

---

## Risks & contingencies (repeated from spec §10 for implementer convenience)

| Risk | Mitigation during implementation |
|---|---|
| Qwen3-Embedding-0.6B download too slow / OOM | First run will take 5-15 minutes; caching to `~/.cache/huggingface` means subsequent runs are instant. If disk full, set `HF_HOME` |
| `sqlite-vec` vec0 MATCH syntax differs from expected | Confirmed syntax: `WHERE embedding MATCH ? AND k = ?` — k placeholder required. If query fails, test against `sqlite-vec` example CLI |
| FTS5 `trigram` on non-ASCII | Task 0 Step 2 already verified SQLite >= 3.34; trigram handles Chinese by 3-character windows, so "Collection 隔离" matches chunks containing that substring |
| `CASCADE` on delete leaves fts/vec rows orphaned | Manual DELETE from `chunks_fts` and `chunks_vec` must precede `DELETE FROM chunks` (see `_delete_chunks_locked`) or happen at client level for delete_collection |
| Contract tests cumulative runtime > 10 min | Qwen3 model is cached module-scope in Task 5's fixture; contract tests build fresh client per test but share embedder via import-level singleton pattern. If too slow: add `scope="session"` to `qmd_client_factory` and reset state between tests |
