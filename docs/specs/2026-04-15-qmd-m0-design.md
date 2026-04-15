# qmd-py M0 实施设计（契约冻结）

**日期**: 2026-04-15
**分支**: `feat/v3-p0-cleanup`
**依据**: `docs/design.md` v3 + `docs/TD.md` M0 章节
**范围**: TD.md T0.1 – T0.8（~5.3 天，预算 2 周）

---

## 0. 目标

把 qmd 的对外表面从"函数式裸露"收敛为"6 个名字的稳定契约"，提供 `FakeQmdClient` 和契约测试 pytest plugin，让下游 Scrivai 在 M0 就能依赖 qmd 的接口（即使真实 SQLite 实现尚未写）。

**非目标**：真实 SQLite / sqlite-vec / GGUF 实现（M1）、性能优化（M2）、删除旧代码（M3）。

## 1. 关键决策（已与用户确认）

| # | 决策 | 理由 |
|---|---|---|
| 1 | 旧代码保留内部，仅从 `qmd/__init__.py` 移除导出 | M0 聚焦契约；M1 可复用旧算法；M3 统一删除 |
| 2 | pydantic 模型放 `qmd/models.py`（包顶层） | v3 changelog 原意；models 是 public API 本身，和 `core/` 平级 |
| 3 | `FakeQmdClient` 用真 BM25 + sentence-transformers (all-MiniLM-L6-v2) | 和真实行为最接近；避免 CLAUDE.md 禁用的 mock/随机数 |
| 4 | M0 `connect()` 返回 `FakeQmdClient`，`db_path` 被忽略并 warning | CLI 契约测试 M0 即可端到端跑；M1 无缝切换 |
| 5 | 新 CLI 在 `qmd/cli/__main__.py`，旧 `cli/main.py` 保留但失去 entry point；`test_cli.py` 加 `@pytest.mark.skip` | 硬切换精神 + 不破坏已有测试骨架 |
| 6 | 契约测试做成 pytest plugin（M0 即完整形态） | T0.5 DoD 明确要求；I0 集成点 Scrivai M0 就要用 |
| 7 | `tests/fixtures/guide_excerpt.md` 自造 ~400 字通用 markdown；支持 `GOVDOC_FIXTURES` env var 覆盖 | GovDoc-Auditor 仓库为空；env var 机制让未来切换零成本 |

## 2. 文件布局

```
qmd/
├── __init__.py          ← 重写：仅导出 6 个名字
├── models.py            ← 新建：pydantic + Protocol
├── cli/
│   ├── main.py          ← 旧：保留，失去 entry point
│   └── __main__.py      ← 新建：argparse + JSON-stdout
├── testing/             ← 新建目录
│   ├── __init__.py      ← 导出 FakeQmdClient / FakeCollection
│   ├── fakes.py         ← Fake 实现
│   └── contract.py      ← pytest plugin
└── core/                ← M0 不动

tests/
├── contract/            ← 新建
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_public_api.py
│   ├── test_models.py
│   ├── test_protocols.py
│   ├── test_fake_implementation.py
│   ├── test_invariants.py
│   └── test_cli_shape.py
├── fixtures/
│   └── guide_excerpt.md ← 新建
└── test_cli.py          ← 加 skip marker
```

`pyproject.toml`：entry point 切到新 CLI；新增 `testing` optional dep；注册 `pytest11` entry point。

## 3. `qmd/models.py` 契约

### 3.1 pydantic 模型

```python
class ChunkRef(BaseModel):
    document_id: str
    chunk_index: int               # 从 0 起
    char_start: int                # UTF-8 字符索引（非字节），闭区间
    char_end: int                  # 闭区间 end，> char_start

class SearchResult(BaseModel):
    chunk_ref: ChunkRef
    text: str
    score: float                   # 融合后总分
    bm25_score: float | None
    vector_score: float | None
    rerank_score: float | None     # 仅 rerank=True 填充
    metadata: dict[str, Any]

class CollectionInfo(BaseModel):
    name: str
    document_count: int
    chunk_count: int
    embedding_dim: int | None      # Fake/未 embed 时 None
```

### 3.2 Protocol

```python
@runtime_checkable
class Collection(Protocol):
    name: str
    def add_document(self, document_id: str, markdown: str,
                     metadata: dict[str, Any] | None = None) -> None: ...
    def delete_document(self, document_id: str) -> None: ...
    def get_document(self, document_id: str) -> dict[str, Any] | None: ...
    def list_documents(self) -> list[str]: ...
    def hybrid_search(self, query: str, top_k: int = 5,
                      rerank: bool = False,
                      filters: dict[str, Any] | None = None
                      ) -> list[SearchResult]: ...
    def info(self) -> CollectionInfo: ...

@runtime_checkable
class QmdClient(Protocol):
    def collection(self, name: str) -> Collection: ...
    def list_collections(self) -> list[CollectionInfo]: ...
    def delete_collection(self, name: str) -> None: ...
    def close(self) -> None: ...

def connect(db_path: str | Path | None = None) -> QmdClient: ...
```

### 3.3 `qmd/__init__.py`

```python
from qmd.models import (ChunkRef, SearchResult, CollectionInfo,
                        Collection, QmdClient, connect)
__all__ = ["ChunkRef", "SearchResult", "CollectionInfo",
           "Collection", "QmdClient", "connect"]
__version__ = "0.1.0"
```

### 3.4 契约不变量（测试覆盖 `design.md §3.1`）

1. `hybrid_search` 结果按 `score` 严格降序
2. `ChunkRef.char_start/char_end` 在原始 markdown 字符串上精确定位
3. `metadata` 透传不解释
4. `filters` 仅支持精确相等匹配
5. 不同 collection 结果不混入
6. `add_document` 同 id 重调 = upsert（幂等）
7. Collection 方法线程安全（进程内）

## 4. `FakeQmdClient` 实现

### 4.1 内部结构

内存字典 + 惰性 BM25 + 真 embedding：

```python
class _FakeCollection:
    name: str
    _docs: dict[str, _DocRecord]
    _chunks: list[_ChunkRecord]
    _lock: threading.Lock
    _embedder: SentenceTransformer | None  # 懒加载，首次 embed 时初始化
    _bm25: BM25Okapi | None                # 惰性重建，脏标记触发

class _ChunkRecord:
    document_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    embedding: np.ndarray          # shape (384,)
```

### 4.2 算法

- **Chunking**：按 `\n\n` 切段（Fake 用极简版，不复用 `core/chunking.py`，保持隔离）；`char_start/end` 通过 `str.find()` 精确计算
- **BM25**：`rank_bm25` 库，tokenization = `text.lower().split()`
- **Embedding**：`SentenceTransformer("all-MiniLM-L6-v2")`，首次 embed 调用时懒加载，`embedding_dim = 384`
- **融合**：RRF（k=60），BM25 top 20 + vector cosine top 20 → RRF → top_k
- **Rerank**：Fake 忽略 rerank 模型，但填 `rerank_score = score`（字段被 exercise）
- **Filters**：`all(chunk.metadata.get(k) == v for k, v in filters.items())`
- **线程安全**：所有 mutating 方法进 `self._lock`

### 4.3 边界

- `get_document` 不存在 → `None`
- `delete_document` / `delete_collection` 不存在 → 静默 no-op
- `collection("foo")` 首次调用 → 自动创建
- `connect(db_path)` 非 `None` → `logger.warning("M0: db_path 被忽略")`

## 5. 契约测试 pytest plugin

### 5.1 注册

```toml
[project.entry-points.pytest11]
qmd_contract = "qmd.testing.contract"
```

### 5.2 Plugin 提供的 fixture

```python
@pytest.fixture
def qmd_client_factory():
    raise NotImplementedError("请在你的 conftest.py 覆盖 qmd_client_factory fixture")

@pytest.fixture
def qmd_client(qmd_client_factory):
    client = qmd_client_factory()
    yield client
    client.close()
```

下游通过覆盖 `qmd_client_factory` 注入自己的实现。qmd 自己的 `tests/contract/conftest.py` 注入 `FakeQmdClient`。

### 5.3 测试分组（~34 个，对齐 DoD）

| 文件 | 数量 | DoD 挂钩 |
|---|---|---|
| `test_public_api.py` | 3 | T0.1: import 表面、旧符号、`__version__` |
| `test_models.py` | 6 | T0.2: 三个 model 往返 + 字段校验 |
| `test_protocols.py` | 2 | T0.3: runtime_checkable + mypy |
| `test_invariants.py` | 12 | §3.1 全部 7 条不变量 |
| `test_fake_implementation.py` | 5 | T0.4: Fake 核心行为 |
| `test_cli_shape.py` | 6 | T0.7: CLI JSON ≡ Python API |

### 5.4 关键测试技术

- **线程安全**：`ThreadPoolExecutor(8)` + 100 次并发 upsert + search，断言 `document_count == 1` 且无异常
- **CLI shape**：`subprocess.run(["qmd", ...])` → 解析 stdout JSON → 对比 Python API `model_dump(mode="json")`；浮点 round 到 6 位；用 `DeepDiff`
- **char 索引**：随机生成 markdown，断言 `md[chunk.char_start:chunk.char_end+1] == chunk.text`

## 6. 新 CLI（`qmd/cli/__main__.py`）

### 6.1 命令（严格对齐 `design.md §3.2`）

```
qmd search     --collection <n> --query <q> [--top-k 5] [--rerank] [--filters '<json>']
qmd collection info  --collection <n>
qmd collection list
qmd document get     --collection <n> --document-id <id>
qmd document add     --collection <n> --document-id <id> --markdown-file <path> [--metadata-json '<json>']
qmd document delete  --collection <n> --document-id <id>
qmd document list    --collection <n>
```

### 6.2 约定

- 路径：`--db-path` > env `QMD_DB_PATH` > 默认 `~/.qmd/db.sqlite`
- 成功 → stdout JSON，exit 0；失败 → stderr `{"error": "..."}`，exit 1
- `search` → `list[SearchResult.model_dump(mode="json")]`
- `collection info` / `list` → `CollectionInfo` / `list[CollectionInfo]`
- `document add` / `delete` → `{"ok": true, "document_id": "..."}`
- `document get` → `{id, markdown, metadata, chunk_count}` 或 `null`

### 6.3 骨架

```python
def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    client = None
    try:
        client = connect(_resolve_db_path(args))
        result = _dispatch(client, args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
```

每个 `_cmd_*` ≤ 20 行，只做参数转换 + 调 Python API + `.model_dump(mode="json")`。

### 6.4 性能

T0.7 要求 P50 < 200ms（不含真实搜索）。`sentence-transformers` 懒加载保证 `list` / `info` 等无 embed 命令不触发模型加载。契约测试对无 embed 命令加 timing 断言（< 500ms 留 buffer）。

## 7. Fixtures

`tests/fixtures/guide_excerpt.md`：自造 ~400 字 markdown 样例，包含 H1/H2/列表/代码块四类结构元素，纯技术描述（**禁止**出现 audit / govdoc / 招标 / 审核 等业务词，符合 namespace 独立原则）。

`tests/contract/conftest.py` 读取 `GOVDOC_FIXTURES` env var，未设置时 fallback 到 `tests/fixtures/`。

## 8. `pyproject.toml` 变更

```toml
[project.scripts]
qmd = "qmd.cli.__main__:main"   # 从 qmd.cli.main:main 切换

[project.optional-dependencies]
testing = ["pytest", "pytest-asyncio",
           "sentence-transformers", "rank-bm25",
           "numpy", "deepdiff"]

[project.entry-points.pytest11]
qmd_contract = "qmd.testing.contract"
```

## 9. 实施顺序（依赖拓扑）

```
1. qmd/models.py                    (T0.2)  0.5d
2. qmd/__init__.py 重写             (T0.1)  0.2d
3. qmd/testing/fakes.py             (T0.4)  1.0d
4. qmd/testing/contract.py 骨架     (T0.5a) 0.5d
5. tests/contract/ 七个测试文件     (T0.5b) 1.5d
6. tests/fixtures/guide_excerpt.md  (T0.8)  0.2d
7. qmd/cli/__main__.py              (T0.7)  1.0d
8. pyproject.toml 调整              (T0.6)  0.2d
9. test_cli.py skip + 全量测试      (T0.6)  0.2d
-----------------------------------------
合计                                        5.3d
```

## 10. DoD 验收清单

| DoD 项 | 验收命令 |
|---|---|
| public API 6 名字 | `python -c "import qmd; print(sorted(qmd.__all__))"` |
| 旧符号不可公开导入 | `python -c "from qmd import Store"` → ImportError |
| pydantic 往返 | `pytest tests/contract/test_models.py` |
| Fake 跑通契约 | `pytest tests/contract/test_fake_implementation.py` |
| 7 条不变量 | `pytest tests/contract/test_invariants.py` |
| CLI ≡ Python API | `pytest tests/contract/test_cli_shape.py` |
| pytest plugin 可用 | `pip install -e .[testing] && pytest --trace-config 2>&1 \| grep qmd_contract` |
| 旧测试不倒退 | `pytest tests/ -x --ignore=tests/test_cli.py --ignore=tests/contract` |
| CLI P50 < 200ms | `hyperfine 'qmd collection list'` |

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| sentence-transformers 80MB 首次下载慢 | CI 缓存 `~/.cache/huggingface/` |
| pytest plugin entry point 注册坑 | T0.5a 先单独验证"空 plugin 能被 pytest 发现"再加内容 |
| `DeepDiff` 对浮点分数误报 | CLI shape 测试 round 到 6 位小数再对比 |
| 线程安全测试不稳定 | 固定 random seed + `np.random.default_rng(42)` |
| M1 切换 `connect()` 破坏契约测试 | 契约测试用 factory fixture 而非直接 import，切换时测试代码零改动 |

## 12. M1 预告（非本 spec 范围）

M1 时：
- 新增 `qmd/core/client.py` (`SqliteQmdClient`) + `qmd/core/collection.py` (`SqliteCollection`)
- `connect()` 切换：`from qmd.core.client import SqliteQmdClient; return SqliteQmdClient(db_path)`
- 契约测试在 Fake 和 Sqlite 两种 factory 下双跑，双绿才能 ship
- Fake 保留永久（给下游单测）
