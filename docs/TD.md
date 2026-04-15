# qmd-py 任务分解（Task Document）

> **版本**: v3（2026-04-15）
> **v2→v3 变更**：T0.2 明确要求 pydantic/Protocol 集中在 `qmd/models.py`；design.md 不再内嵌代码。**不新增外部依赖**——qmd 仍自包含。

**依据**: `design.md` + `/home/iomgaa/Projects/GOVDOC_PROGRAM_PLAN.md`
**开发分支**: `feat/v3-p0-cleanup`（原 `feat/m0-contract-freeze` 合并到此）

---

## 里程碑总览

| 里程碑 | 交付 | 集成点 |
|---|---|---|
| M0（Week 1-2） | 契约冻结 + Fake 实现 + 契约测试套件 | I0：`pytest tests/contract/` 全绿 |
| M1（Week 3-5） | 真实 SQLite + embedding + BM25 + RRF 实现 | I1：Scrivai 跑小 fixture 能召回正确分块 |
| M2（Week 6-7） | 性能优化 + 批量 API + rerank 调优 | I2：10万 chunk 规模达性能基线 |
| M3（Week 8） | 打包 PyPI 0.1.0 + 清理旧代码 | I3：`git grep` 旧符号零结果 |

---

## M0: 契约冻结（Week 1-2）

### T0.1 重写 `qmd/__init__.py` 为新 public API
- **DoD**:
  - `qmd/__init__.py` 仅导出 `ChunkRef, SearchResult, CollectionInfo, Collection, QmdClient, connect`
  - 旧符号（`create_store, Store, NamedCollection, LLMBackend, search, BackendType, Database, ...`）在 `__init__.py` 中**不再出现**
  - `from qmd import *` 得到上述 6 个名字
- **依赖**: 无
- **优先级**: P0
- **契约测试挂钩**: `tests/contract/test_public_api.py::test_import_surface`
- **估时**: 0.5d

### T0.2 写 pydantic 模型（`qmd/core/models.py`）
- **DoD**:
  - `ChunkRef, SearchResult, CollectionInfo` 字节级匹配 `design.md §3`
  - 所有字段有 docstring
  - `model_dump()` / `model_validate()` 往返稳定
- **依赖**: T0.1
- **优先级**: P0
- **契约测试挂钩**: `tests/contract/test_models.py`
- **估时**: 0.5d

### T0.3 实现 `QmdClient / Collection` 的 Protocol
- **DoD**:
  - `qmd/core/client.py`、`qmd/core/collection.py` 定义 Protocol
  - 所有方法签名字节级匹配 `design.md §3`
  - 类型检查通过（`mypy qmd/core/`）
- **依赖**: T0.2
- **优先级**: P0
- **契约测试挂钩**: `tests/contract/test_protocols.py`
- **估时**: 0.5d

### T0.4 实现 `qmd.testing.fakes` — `FakeQmdClient` / `FakeCollection`
- **DoD**:
  - 纯内存字典实现，满足 Protocol
  - 支持 add / update / delete / hybrid_search（简单 BM25 评分 + 随机向量）
  - `char_start/end` 真实计算
  - Scrivai 单测可以 `from qmd.testing import FakeQmdClient`
- **依赖**: T0.3
- **优先级**: P0
- **契约测试挂钩**: `tests/contract/test_fake_implementation.py`（整套契约跑在 Fake 上全绿）
- **估时**: 1d

### T0.5 契约测试套件（`qmd/testing/contract.py`）
- **DoD**:
  - pytest plugin 形态：`@pytest.fixture` 接收 `qmd_client`，跑一套 ~30 个测试
  - 覆盖 `design.md §3.1` 的全部不变量
  - 可被 Scrivai 的测试复用（pip install qmd[testing] 后 `pytest --plugin qmd.testing.contract`）
- **依赖**: T0.4
- **优先级**: P0
- **契约测试挂钩**: 本身就是
- **估时**: 1.5d

### T0.6 仓库清理
- **DoD**:
  - 旧 CLI 命令入口暂时保留在 `cli/` 但不影响 public API
  - MCP 服务器保留但不 import 旧 API
  - `pyproject.toml` 的 entry points 更新到新 API
- **依赖**: T0.1
- **优先级**: P1
- **估时**: 0.5d

### T0.7 CLI JSON-stdout 子命令
- **DoD**:
  - `qmd/cli/__main__.py`：argparse 路由 `search / collection {info,list} / document {get,add,delete,list}`
  - 所有命令打 JSON 到 stdout，error 到 stderr，退出码正确
  - 路径优先级：`--db-path` > `QMD_DB_PATH` env > 默认
  - 在 `pyproject.toml` 注册 `qmd` entry point
  - **CLI 输出 JSON 与 Python API `model_dump(mode="json")` 严格一致**——契约测试比对
  - 每命令 P50 < 200ms（不含真实搜索）
- **依赖**: T0.4
- **优先级**: P0
- **契约测试挂钩**: `tests/contract/test_cli_shape.py`
- **估时**: 1d

### T0.8 Fixture 接入
- **DoD**:
  - `tests/fixtures/` 挂载 GovDoc-Auditor 的 fixtures（通过 conftest.py 指定 `FIXTURE_ROOT`）
  - 契约测试能跑 `guide_excerpt.md` 作为样例输入
- **依赖**: fixture 就位
- **优先级**: P0
- **估时**: 0.5d

**M0 DoD 汇总**: T0.1-T0.8 全完成；`pytest tests/contract/` 全绿（含 CLI 契约）；I0 通过。

---

## M1: 真实实现（Week 3-5）

### T1.1 搬移旧 chunking 算法到新结构
- **DoD**:
  - 从旧 `qmd/core/chunking.py` 搬到新位置，保留算法
  - 新算法仅被 `Collection.add_document` 内部调用，不对外暴露
  - 单测：同一输入 chunk 结果和旧实现一致（回归测试）
- **依赖**: T0.3
- **优先级**: P0
- **估时**: 1d

### T1.2 SQLite schema + sqlite-vec + FTS5
- **DoD**:
  - `qmd/core/db.py` 新版：表 `collections / documents / chunks / embeddings`
  - FTS5 虚表挂在 `chunks.text` 上
  - sqlite-vec 虚表挂 embedding
  - 迁移测试：旧库文件不直接兼容（M0 已宣布硬切换），提供 `qmd migrate` CLI 重建
- **依赖**: T1.1
- **优先级**: P0
- **估时**: 2d

### T1.3 Embedding 后端（sentence_tf）
- **DoD**:
  - `qmd/llm/base.py` 定义 `EmbeddingBackend` 接口
  - sentence_tf 后端调用 Qwen/Qwen3-Embedding-0.6B（HuggingFace checkpoint）
  - 自动 batch（默认 32，GPU 自动提升）
- **依赖**: T1.2
- **优先级**: P0
- **估时**: 1.5d

### T1.4 BM25 + Vector + RRF
- **DoD**:
  - `Collection.hybrid_search` 真实实现
  - BM25 top_k=20 + Vector top_k=20 → RRF 合并 → 返回 top_k
  - 契约测试（T0.5）在真实实现上全绿
- **依赖**: T1.3
- **优先级**: P0
- **估时**: 1.5d

### T1.5 Rerank（Qwen3-Reranker）
- **DoD**:
  - `hybrid_search(rerank=True)` 开启 rerank
  - `SearchResult.rerank_score` 填充
  - 可通过 `qmd.yaml` 关闭
- **依赖**: T1.4
- **优先级**: P1
- **估时**: 1d

### T1.6 `QmdClient.connect` 真实实现
- **DoD**:
  - 管理 SQLite 连接池
  - 首次连接自动初始化 schema
  - 支持 `db_path=None`（默认 `~/.qmd/db.sqlite`）
- **依赖**: T1.2
- **优先级**: P0
- **估时**: 0.5d

### T1.7 对接 fixture 的 smoke test
- **DoD**:
  - 加载 `guide_excerpt.md` → `Collection.add_document`
  - `hybrid_search("围标串标")` 返回的 top-1 chunk 包含关键词"串通投标"或类似
  - **I1 集成节点前通过**
- **依赖**: T1.4
- **优先级**: P0
- **估时**: 0.5d

**M1 DoD**: 契约测试在真实 SQLite 实现上全绿 + I1 通过。

---

## M2: 性能 & 批量（Week 6-7）

### T2.1 批量 API `Collection.add_documents(batch)`
- **DoD**: 新增到契约（走 §8 变更流程，M1 末提 PR），单次 commit 多文档；性能比循环 add 快 ≥3x
- **依赖**: T1.2
- **优先级**: P0
- **估时**: 1d

### T2.2 Embedding 并发 + batch size 调优
- **DoD**: 100 页 markdown embedding < 30s（GPU）/ < 120s（CPU）
- **依赖**: T1.3
- **优先级**: P1
- **估时**: 1d

### T2.3 10万 chunk 规模压测
- **DoD**: P95 `hybrid_search(top_k=5)` < 500ms；压测脚本放 `tests/perf/`
- **依赖**: T2.1 + T2.2
- **优先级**: P0
- **估时**: 1.5d

### T2.4 rerank 性能调优（batch + quantization）
- **DoD**: rerank 开销 < 200ms / query（top_k=20）
- **依赖**: T1.5
- **优先级**: P2
- **估时**: 1d

---

## M3: 打包发布（Week 8）

### T3.1 清理旧代码
- **DoD**:
  - `git grep -E "create_store|NamedCollection|old_.*"` 零结果
  - 旧 `e2e_full.py` / `e2e_test.py` / `e2e_validate.py` 删除或重写
  - `README.md` / `README_CN.md` 更新到新 API
- **依赖**: 所有 M2 完成
- **优先级**: P0
- **估时**: 1d

### T3.2 pyproject.toml → version 0.1.0
- **DoD**: `pip install -e .` 正常；`python -c "import qmd; print(qmd.__version__)"` 输出 0.1.0
- **依赖**: T3.1
- **优先级**: P0
- **估时**: 0.5d

### T3.3 （可选）发布到私有 PyPI
- **DoD**: `pip install qmd==0.1.0 --index-url <私有源>` 在干净环境能装
- **依赖**: T3.2
- **优先级**: P1
- **估时**: 0.5d

### T3.4 CHANGELOG
- **DoD**: 标明 0.1.0 相较旧版本是**完全重写**，不兼容
- **依赖**: T3.1
- **优先级**: P1
- **估时**: 0.2d

---

## Deprecation Target（M3 验收清单）

以下旧符号在 `qmd-py/qmd/` 源码中 **零出现**：

```
create_store
create_llm_backend
load_config
init_schema
open_database
get_db_path
ensure_db_dir
BackendType
NamedCollection
Store  (作为公开导出)
search  (作为公开函数，不含类方法)
LLMBackend  (作为公开导出)
```

验收脚本：
```bash
cd /home/iomgaa/Projects/qmd-py
for sym in create_store create_llm_backend NamedCollection BackendType; do
  matches=$(git grep -c "\\b$sym\\b" -- 'qmd/**/*.py' | grep -v ':0$' || true)
  if [ -n "$matches" ]; then echo "FAIL: $sym still present: $matches"; exit 1; fi
done
echo "OK: all deprecated symbols removed"
```

---

## 跨项目集成任务

这些任务需要和 Scrivai 会话对接，放在对应集成点：

| 任务 | 集成点 | 说明 |
|---|---|---|
| 提供 `qmd.testing` 给 Scrivai | I0 | Scrivai 在 M0 就需要 `FakeQmdClient` 跑自己的契约测试 |
| fixture 路径约定 | I0 | Scrivai 和 qmd 都通过环境变量 `GOVDOC_FIXTURES` 定位 |
| 批量 API `add_documents` 定义 | I1 → I2 间 | 走 PLAN §8 变更流程 |

---

## 风险 & 纠偏

- **风险**: sqlite-vec 在某些平台编译失败
  - **缓解**: M0 就在三方 CI 跑安装测试
- **风险**: 旧代码搬移时算法行为偏移
  - **缓解**: T1.1 的回归测试必须跑同一 fixture 比对旧行为
- **风险**: Scrivai 误以为 qmd 有某方法
  - **缓解**: 契约测试是**单一真相**；Scrivai 在 Fake 上跑过，真实实现必然也过

---

## 日常节奏

- 每天：跑 `pytest` 全绿才 commit
- 每周五：对照 `GOVDOC_PROGRAM_PLAN.md §11` 的偏移检查清单自检
- M0/M1/M2/M3 末：在 `INTEGRATION_ISSUES.md` 汇报里程碑交付
