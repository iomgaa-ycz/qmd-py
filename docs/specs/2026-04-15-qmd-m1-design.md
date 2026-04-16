# qmd-py M1 实施设计

**日期**：2026-04-15
**作者**：brainstorming 产出
**依据**：`docs/design.md` v3、`docs/TD.md` v3、M0 交付（tag `m0-contract-freeze`）
**M1 目标**：落地真实 `SqliteQmdClient`，让 M0 契约测试在 Fake 和 Sqlite 上双参数化全绿；I1 smoke test 通过；`qmd/` 下无死代码。

---

## 1. 八条关键决策（对 TD.md 的差异）

| # | 决策项 | 选项 | 备注 |
|---|---|---|---|
| 1 | Embedding 后端 | **只做 sentence_tf**；llama_cpp 推 M2 | 本地无 llama-cpp-python 和 GGUF；偏离 design §9 默认，但不违反契约 |
| 2 | 默认模型 | **Qwen/Qwen3-Embedding-0.6B（1024 维）**；Fake 同步升级 | 契约首次运行下载 ~1.2GB |
| 3 | 旧代码策略 | **D：算法重写 + 旧文件彻底删除** | 不留任何未被活代码引用的文件 |
| 4 | Rerank（T1.5） | **M1 no-op**：`rerank=True` 返回 RRF 结果，`rerank_score=None` | docstring 明确标注"M1 不实现" |
| 5 | 契约测试执行 | **pytest 参数化双跑** `params=["fake", "sqlite"]` | 测试节点名带后缀 |
| 6 | `connect()` 行为 | 默认 `~/.qmd/db.sqlite`；`QMD_DB_PATH` 覆盖；自动建目录/文件/schema；单连接 + `threading.Lock`；sqlite-vec 连接时加载 | |
| 7 | Chunking 参数 | **512 tokens / 64 overlap**，启发式估算 `len(text)//2` | 同步修正 CLAUDE.md §5.3 |
| 8 | `qmd.yaml` 配置 | **M1 不引入**，所有参数硬编码 | 记录到 M2 挂起清单 |

## 2. M2 挂起清单（M1 不做）

- `qmd.yaml` 配置加载（目前所有参数硬编码于各模块顶部常量）
- `llama_cpp` embedding 后端 + GGUF 模型下载
- 真实 rerank（候选：bge-reranker-v2-m3 或 Qwen3-Reranker）
- 批量 API `Collection.add_documents(batch)`（T2.1）
- 精确 Qwen3 tokenizer 计数（替换启发式）
- 性能优化 + 10 万 chunk 压测（T2.3）

## 3. 文件结构（M1 后）

```
qmd/
├── __init__.py                    # 不变（6 个导出）
├── __main__.py                    # 不变
├── models.py                      # 改 connect() 指向 SqliteQmdClient
├── core/
│   ├── __init__.py                # 空
│   ├── chunking.py                # 新：纯函数 chunk_document()
│   ├── retrieval.py               # 新：纯函数 rrf_fuse()
│   ├── embedding.py               # 新：Qwen3-Embedding-0.6B 封装
│   ├── db.py                      # 新：连接 + schema
│   ├── collection.py              # 新：SqliteCollection
│   └── client.py                  # 新：SqliteQmdClient
├── cli/
│   ├── __init__.py                # 不变
│   └── __main__.py                # 不变
├── testing/
│   ├── __init__.py                # 不变
│   ├── fakes.py                   # 改：embedder 切到 Qwen3-Embedding-0.6B
│   └── contract.py                # 不变
└── utils/                         # 保留仍被活代码 import 的文件；其余删

# 删除清单
[del] qmd/mcp/                                  (broken，整个目录)
[del] qmd/llm/                                  (整个目录)
[del] qmd/cli/main.py search.py embed.py collection.py context.py formatter.py
[del] qmd/core/store.py config.py document.py watcher.py（以及旧 db.py/chunking.py/retrieval.py）
[del] tests/test_{chunking,cli,config,db,document,e2e,formatter,
                   llm,llm_base,llm_flagembed,llm_llama_cpp,
                   llm_models,llm_sentence_tf,retrieval,store,watcher}.py
[del] scripts/（如仍引用旧 API）
```

**退出验收**：`qmd/` 下每个 `.py` 都被 `qmd.__init__` 的 6 个导出或新 CLI 或 contract test 直接/间接使用。

## 4. SQLite Schema

```sql
-- 1. collections
CREATE TABLE collections (
    name       TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL
);

-- 2. documents
CREATE TABLE documents (
    collection  TEXT NOT NULL,
    id          TEXT NOT NULL,
    markdown    TEXT NOT NULL,
    metadata    TEXT NOT NULL,          -- JSON 字符串
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (collection, id),
    FOREIGN KEY (collection) REFERENCES collections(name) ON DELETE CASCADE
);

-- 3. chunks
CREATE TABLE chunks (
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
CREATE INDEX idx_chunks_doc ON chunks(collection, document_id);

-- 4. FTS5 独立虚表（BM25）
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    tokenize='trigram'                  -- 中文友好，SQLite 3.34+ 内置
);

-- 5. sqlite-vec 虚表（1024 维 float32）
CREATE VIRTUAL TABLE chunks_vec USING vec0(
    embedding FLOAT[1024]
);
```

**关键点**：
- 三表 rowid 对齐（`chunks.rowid == chunks_fts.rowid == chunks_vec.rowid`），`add_document` / `delete_document` 手动同步维护
- `chunks_fts` 独立表（非 contentless 镜像），省去触发器；代价：text 存两份（MVP 可接受）
- `metadata` 用 `json_extract(..., '$.key') = 'value'` 过滤
- 所有删除走 `ON DELETE CASCADE`（documents→chunks）；FTS5/vec0 需手动先删（无 FK）
- FTS5 `trigram` tokenizer 要求 SQLite ≥ 3.34；启动时检查并明确抛错

## 5. 核心组件接口

### 5.1 `qmd/core/chunking.py`

```python
@dataclass(frozen=True)
class Chunk:
    text: str
    char_start: int
    char_end: int

def chunk_document(text: str, size: int = 512, overlap: int = 64) -> list[Chunk]:
    """按语义边界切分 markdown。
    - token 估算：len(text) // 2（中文保守）
    - 断点优先级：H1/H2/H3 > 代码块边界 > 分隔线 > 空行 > 换行
    - 平方距离衰减：靠近目标位置的断点得分更高
    - 代码块保护：绝不在 ``` 内切分
    返回 char_start/char_end 精确对应原始 markdown 索引。"""
```

### 5.2 `qmd/core/embedding.py`

```python
class Embedder:
    """Qwen3-Embedding-0.6B via sentence-transformers。懒加载。"""
    DIM: int = 1024
    MODEL_NAME: str = "Qwen/Qwen3-Embedding-0.6B"

    def __init__(self) -> None:
        self._model = None  # 懒加载

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """批量 embed。返回 len(texts) × 1024 的嵌套 list（便于 JSON 序列化和 sqlite-vec 写入）。"""
```

### 5.3 `qmd/core/retrieval.py`

```python
def rrf_fuse(
    rankings: list[list[int]],  # 每个元素是按相关度降序的 rowid list
    k: int = 60,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion。返回 (rowid, rrf_score) 按 score 严格降序。
    rrf_score = sum(1 / (k + rank_i)) over all rankings where rowid appears。"""
```

### 5.4 `qmd/core/db.py`

```python
SCHEMA_SQL: str = """..."""  # 上面 §4 的所有 CREATE

def open_connection(db_path: Path) -> sqlite3.Connection:
    """打开 SQLite 连接，执行：
    1. mkdir -p 父目录
    2. sqlite3.connect(db_path)
    3. PRAGMA foreign_keys = ON
    4. conn.enable_load_extension(True); sqlite_vec.load(conn)
    5. 检查 SQLite 版本 >= 3.34（trigram 需要）；不达抛 RuntimeError
    6. executescript(SCHEMA_SQL)  # 幂等
    返回 conn。"""
```

### 5.5 `qmd/core/collection.py`

`SqliteCollection` 实现 `Collection` Protocol（`qmd/models.py`）：

| 方法 | 语义 |
|---|---|
| `add_document(id, markdown, metadata=None)` | upsert：先删旧 chunks（chunks/fts/vec 三表），再 UPSERT documents，然后 chunk + batch embed + 三表批量插入。全流程单事务。|
| `update_document(id, markdown, metadata=None)` | 复用 `add_document`（幂等） |
| `delete_document(id)` | DELETE documents 级联 chunks；手动 DELETE chunks_fts/chunks_vec（按 rowid） |
| `get_document(id)` | SELECT documents；返回 dict，不存在返回 None |
| `list_documents(filters=None)` | 按 metadata JSON 过滤；返回 list[dict] |
| `get_chunks(document_id)` | 返回该文档所有 ChunkRef（按 chunk_index） |
| `hybrid_search(query, top_k=5, rerank=False, filters=None)` | 见下 |

`hybrid_search` 流程：
1. `embed([query])` → `query_vec`（1024 维）
2. BM25 检索：`SELECT rowid FROM chunks_fts WHERE text MATCH ? ORDER BY rank LIMIT 20`，WHERE 附带 collection + filters 过滤
3. Vector 检索：`SELECT rowid FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 20`，同样加过滤
4. `rrf_fuse([bm25_rowids, vec_rowids], k=60)` → 取前 `top_k`
5. 按 rowid 从 `chunks` JOIN `documents` 读详情，构造 `list[SearchResult]`
6. `SearchResult.score = rrf_score`；`rerank_score = None`（M1 永远）
7. `rerank` 参数本 M1 忽略（docstring 明标注）
8. 方法体全包在 `self._lock` 里（线程安全）

**硬编码常量**（集中在 `collection.py` 顶部，M2 迁 yaml）：
```python
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 64
RRF_K = 60
BM25_TOP_K = 20
VECTOR_TOP_K = 20
EMBEDDING_BATCH_SIZE = 32
```

### 5.6 `qmd/core/client.py`

```python
class SqliteQmdClient:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn = open_connection(db_path)
        self._lock = threading.Lock()
        self._embedder = Embedder()
        self._collections: dict[str, SqliteCollection] = {}

    def collection(self, name: str) -> Collection:
        """自动创建 collections 行（幂等），缓存 SqliteCollection 实例。"""

    def list_collections(self) -> list[CollectionInfo]: ...
    def delete_collection(self, name: str) -> None: ...
    def close(self) -> None: ...
```

### 5.7 `qmd/models.py::connect`（修改）

```python
def connect(db_path: str | Path | None = None) -> QmdClient:
    if db_path is None:
        import os
        db_path = os.environ.get("QMD_DB_PATH") or Path.home() / ".qmd" / "db.sqlite"
    from qmd.core.client import SqliteQmdClient
    return SqliteQmdClient(Path(db_path))
```

`FakeQmdClient` 不再是 `connect()` 默认值；下游测试通过 `from qmd.testing import FakeQmdClient` 直接实例化。

## 6. 契约测试参数化

```python
# tests/contract/conftest.py
import pytest
from qmd.testing import FakeQmdClient
from qmd.core.client import SqliteQmdClient

@pytest.fixture(params=["fake", "sqlite"])
def qmd_client_factory(request, tmp_path):
    if request.param == "fake":
        def factory(): return FakeQmdClient()
    else:
        def factory(): return SqliteQmdClient(tmp_path / "test.sqlite")
    yield factory

@pytest.fixture
def qmd_client(qmd_client_factory):
    client = qmd_client_factory()
    yield client
    client.close()
```

预计：M0 的 ~94 条契约测试 × 2 params = ~188 条。Qwen3-Embedding-0.6B 模型文件被 sentence-transformers cache 后，整套跑时间控制在 2 分钟内（目标）。

## 7. Smoke Test（I1）

`tests/contract/test_smoke.py`（新文件，参数化 fixture 自动双跑）：

```python
def test_smoke_guide_excerpt(qmd_client, guide_excerpt_markdown):
    col = qmd_client.collection("smoke")
    col.add_document("guide", guide_excerpt_markdown)
    results = col.hybrid_search("Collection 隔离", top_k=3)
    assert len(results) >= 1
    assert any("Collection" in r.chunk.text for r in results)
```

说明：fixture `tests/fixtures/guide_excerpt.md` 是 M0 已有的中性 markdown，不含业务词。query `"Collection 隔离"` 出现在 fixture 的"Collection"章节。

## 8. 实施顺序（先立后破）

1. `core/chunking.py`（纯函数，无依赖）+ 单测
2. `core/retrieval.py`（纯函数）+ 单测
3. `core/embedding.py` + 单测（可跳过真实模型加载，mock tokenize；真实加载放 contract test）
4. `core/db.py` + 单测
5. `core/collection.py` + 契约测试（参数化 fixture 先只跑 `sqlite` 子集）
6. `core/client.py` + 契约测试全量参数化双跑
7. 切换 `qmd/models.py::connect`
8. Smoke test（`test_smoke_guide_excerpt`）
9. 升级 `testing/fakes.py` 的 embedder 到 Qwen3-Embedding-0.6B
10. 一次性删除所有旧文件（cli/main.py 等 + mcp/ + core 旧 + llm/ + 11 个旧测试），测试全绿才 commit
11. 更新 CLAUDE.md §5.3
12. 最终 DoD 检查

每步独立 commit，回退点清晰。

## 9. DoD 检查清单

- [ ] `pytest tests/contract/ -v` 全绿（~188 条参数化）
- [ ] `ls qmd/core/` = `__init__.py chunking.py client.py collection.py db.py embedding.py retrieval.py`
- [ ] `ls qmd/` 不含 `mcp/`、`llm/`
- [ ] `ls qmd/cli/` = `__init__.py __main__.py`
- [ ] `git grep -nE "create_store|NamedCollection|BackendType|LLMBackend|create_llm_backend" qmd/` 零结果
- [ ] `test_smoke_guide_excerpt[fake]` 和 `[sqlite]` 均绿
- [ ] CLI 回归（手动）：`qmd collection list` / `qmd document add/list/get/delete` / `qmd search` 在真实 SQLite 后端工作
- [ ] CLAUDE.md §5.3 chunking 参数更新到 512/64
- [ ] spec 里明确记录 M2 挂起清单

## 10. 风险与预案

| 风险 | 缓解 |
|---|---|
| Qwen3-Embedding-0.6B 首次下载慢（~1.2GB） | 在 spec 和 README 里记录；contract test 可加 `pytest.mark.slow`（可选） |
| FTS5 `trigram` tokenizer 需 SQLite ≥ 3.34 | `open_connection` 启动时检查，不达要求抛 `RuntimeError` 明确报错 |
| sqlite-vec 维度不匹配 | `Embedder.DIM` 作为单一真相，`db.py` 的 schema 模板里用 f-string 注入 `{Embedder.DIM}`，避免漂移 |
| Fake 和 Sqlite 行为细节漂移 | 契约测试参数化双跑是唯一真相，新加测试必须通过两边 |
| sentence-transformers 首次加载 OOM / 磁盘不足 | README 明确下载要求；本地开发者可 `HF_HOME` 重定向 |
| 清理旧文件误删仍被引用的文件 | 第 10 步前跑 `python -c "import qmd; import qmd.cli.__main__"` 确认，失败则具体查缺 |

## 11. 与 design.md / TD.md 的差异备忘

| 项 | design/TD 原文 | M1 实际 | 理由 |
|---|---|---|---|
| Embedding 默认 | llama_cpp + embeddinggemma-300M GGUF（§9） | sentence_tf + Qwen3-Embedding-0.6B | 环境无 llama-cpp-python；Qwen3 质量更好 |
| Rerank | `hybrid_search(rerank=True)` 开启 rerank，`rerank_score` 填充（T1.5） | M1 no-op，`rerank_score=None` | T1.5 P1，M1 P0 优先 |
| Chunking 参数 | 512/64（design §4.1）vs 900/135（CLAUDE §5.3） | 512/64 | 对齐 Qwen3 max_seq_length；CLAUDE 同步更新 |
| qmd.yaml | §9 展示完整 schema | M1 硬编码 | YAGNI；M2 引入 |
| 旧代码 | TD T0.6 "MCP 保留不 import 旧 API" | MCP 彻底删（broken） | MCP 当前已破；延迟维护成本大 |
| Chunking 搬移 | T1.1 "搬移旧算法，保留算法，回归对齐" | 重写（可参考旧算法），不做回归对齐 | 旧算法要和新 public API + 新 schema 解耦；回归对比价值低（输出契约变了） |

---

**本 spec 经 brainstorming 产出并用户确认。实施计划见 `docs/plans/2026-04-15-qmd-m1-implementation.md`（由 writing-plans skill 产出）。**
