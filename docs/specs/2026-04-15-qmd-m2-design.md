# qmd-py M2 Design: 批量 API + 真实 Rerank + 性能基线

**日期**: 2026-04-15
**范围**: TD.md M2（T2.1–T2.4）+ 回补 M1 跳过的 T1.5 真实 rerank
**分支**: `feat/m2-batch-rerank-perf`（从 `feat/m1-sqlite-real` 切出）
**交付 tag**: `m2-perf-baseline`

## 1. 目标

1. 批量 `add_documents(docs: list[dict])` 纳入契约，≥3x 快于循环单加
2. 真实 rerank 实现（Qwen3-Reranker-0.6B via transformers HF checkpoint，不走 GGUF）
3. 引入 qmd.yaml 配置系统（chunking / embedding / rerank / retrieval 可配）
4. Embedding 吞吐优化（GPU/CPU 自动 batch_size），100p markdown < 30s(GPU) / < 120s(CPU)
5. 10 万 chunk 规模 hybrid_search P95 < 500ms 基线
6. rerank P95 < 200ms/query（top_k=20）
7. 文档清理：CLAUDE.md / design.md 去除 llama-cpp-python 路径

## 2. 关键决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | Rerank 走 transformers HF checkpoint，不走 GGUF | 与 M1 sentence-transformers 技术栈统一，避开 GGUF logprobs 手实现 |
| D2 | 批量 API 签名 `add_documents(docs: list[dict])`，dict 含 `document_id/markdown/metadata` | 与 CLI `document add` 参数结构呼应，字段最直观 |
| D3 | 批量事务原子性：任一失败整批回滚 | "批量入库"的语义直觉；部分失败返回 result list 会让调用方困惑 |
| D4 | 批量内部用单次大 batch encode（不并发多线程） | Qwen3 GPU batch 吞吐随 batch 增大单调上升；并发会争 GPU lock |
| D5 | qmd.yaml 加载 3 层优先级：`config_overrides` kwargs > `{db_path同目录}/qmd.yaml` > pydantic 默认 | 简化为单一文件来源，避免多层隐式查找 |
| D6 | M2 rerank 排序策略 = pure rerank_score 替换 RRF；position-aware blending 延后 M3 | blending 收益需真实语料 AB 验证；M2 先跑通 |
| D9 | `hybrid_search(rerank=True)` 方法参数优先于 `config.rerank.enabled`；config 字段仅为 CLI / 调用方 UI 默认值 | 方法参数显式 override 是 Python API 惯例；config 的 enabled 用于 CLI 默认 `--rerank` 行为 |
| D7 | 10 万 chunk 语料优先 wikipedia-zh 流式抽取，失败 fallback 合成 | 真实分布更有说服力；流式抽取控制下载量 |
| D8 | rerank 测试用真模型（非 mock），通过 `@pytest.mark.reranker` 控制 CI 跳过 | 测试必须验证真实模型加载 + 打分正确性 |

## 3. 文件变更清单

### 新增
- `qmd/core/config.py` — `QmdConfig` pydantic + yaml loader
- `qmd/core/rerank.py` — `Reranker` 类（Qwen3-Reranker 类级单例）
- `tests/contract/test_batch.py` — 批量 upsert 契约（fake + sqlite 参数化）
- `tests/contract/test_rerank.py` — rerank_score 填充 + 排序影响（sqlite only，`@pytest.mark.reranker`）
- `tests/unit/test_config.py` — yaml 加载 / 覆盖优先级 / 错误处理
- `tests/unit/test_rerank.py` — Reranker 接口（mock 模型）
- `tests/perf/conftest.py` — wikipedia-zh 流式 / 合成 fallback / DB 缓存
- `tests/perf/test_hybrid_search_p95.py` — `@pytest.mark.perf` P95 基准
- `tests/perf/test_rerank_latency.py` — `@pytest.mark.perf` rerank 延迟基准
- `docs/plans/m3-backlog.md` — M3 延后事项清单

### 修改
- `qmd/models.py` — `Collection` Protocol 新增 `add_documents`；docstring 补 `rerank_score`
- `qmd/core/client.py` — `connect(db_path, config_overrides=None)` 读 yaml
- `qmd/core/collection.py` — `add_documents` 实现 + rerank 接入 + 从 config 读常量
- `qmd/core/embedding.py` — GPU/CPU 自动 batch_size + 从 config 读
- `qmd/testing/fakes.py` — `FakeCollection.add_documents` + fake rerank（hash 伪分数）
- `CLAUDE.md` — §2.2 / §2.3 / §7 去 llama-cpp-python
- `docs/design.md` — §4.1 / §9 去 GGUF 路径
- `pyproject.toml` — 主依赖新增 `pyyaml`, `transformers`；新增 `[perf]` extras

## 4. Config Schema

```yaml
# {db_path 同目录}/qmd.yaml（可选；缺失即走默认）
chunking:
  size: 512
  overlap: 64
  strategy: "semantic"

embedding:
  backend: "sentence_tf"
  model_name: "Qwen/Qwen3-Embedding-0.6B"
  dim: 1024
  batch_size: "auto"     # auto → GPU=64, CPU=16

rerank:
  enabled: false
  backend: "sentence_tf"
  model_name: "Qwen/Qwen3-Reranker-0.6B"
  top_k_candidates: 40   # RRF 后喂给 reranker 的候选数

retrieval:
  rrf_k: 60
  bm25_top_k: 20
  vector_top_k: 20
```

**加载优先级**（高 → 低）：
1. `connect(db_path, config_overrides={...})` — 测试/临时调整
2. `{db_path 同目录}/qmd.yaml` — 生产场景
3. Pydantic 默认值 — yaml 缺失不报错

**错误处理**：
- yaml 语法错或 schema 错 → `ConfigError`，消息指明字段路径
- `connect` 从不因 yaml 缺失失败

## 5. Batch add_documents 契约

```python
class Collection(Protocol):
    def add_documents(self, docs: list[dict]) -> None: ...
```

**契约不变量**：
- 每 dict 必含 `document_id: str`、`markdown: str`、`metadata: dict`（缺字段 → `ValueError`，入库前 fail-fast 全检）
- 原子事务：任一失败整批回滚
- upsert 语义：同 `add_document`，批内同 id 重复以最后一个为准
- 空 list 合法（no-op）
- 线程安全（复用 `_lock`）

**SqliteCollection 执行流**：
```
with self._lock:
    validate all docs (fail-fast)
    BEGIN
    try:
        for doc in docs:
            upsert documents row
            delete old chunks (if upserting)
            chunk markdown → append to all_chunks
        all_vecs = Embedder.embed([c.text for c in all_chunks])   # 单次大 batch
        executemany INSERT chunks
        executemany INSERT chunks_fts
        executemany INSERT chunks_vec
        COMMIT
    except:
        ROLLBACK; raise
```

**FakeCollection**：遍历 `add_document`，失败前做 deepcopy snapshot 回滚。

## 6. Rerank 实现（Qwen3-Reranker-0.6B）

**打分机制**（官方方法）：
```
prompt = f"Given a query '{query}', judge whether the Document '{doc}' meets the requirements. Note that the answer can only be 'yes' or 'no'."
logits = model(prompt).logits[0, -1]
score = softmax(logits[[yes_id, no_id]])[0]    # P(yes) ∈ [0, 1]
```

**`Reranker` 类结构**：
- `MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B"`
- `_shared_model / _shared_tokenizer / _shared_lock` 类级单例（同 Embedder 策略防 GPU OOM）
- `_load()` → `AutoTokenizer.from_pretrained` + `AutoModelForCausalLM.from_pretrained`（fp16 on GPU）
- `score(query: str, docs: list[str]) -> list[float]`：批量 padding + forward + 提取 yes/no logits；空 list 不触发加载
- `torch.inference_mode()` 包裹 forward 减开销

**`hybrid_search` 集成**：
```
1. BM25 top-20 + Vector top-20 → RRF fuse → 取 top-N (N = config.rerank.top_k_candidates, 默认 40)
2. if rerank=True:    # 方法参数 override config；config.rerank.enabled 仅作默认开关由调用方读取
     scores = Reranker().score(query, [c.text for c in candidates])
     fill cand.rerank_score = s
     sort by rerank_score desc
   else:
     rerank_score = None
3. return top_k
```

**FakeCollection rerank**：`hash((query, text))` 稳定伪分数填充 `rerank_score`，仅保证字段填充 + 排序单调。

## 7. Perf 测试策略

### 10 万 chunk 语料
`tests/perf/conftest.py`:
```python
@pytest.fixture(scope="session")
def large_corpus_db() -> Path:
    cache = Path("tests/perf/.cache/corpus.sqlite")
    if cache.exists(): return cache
    try:
        docs = _load_wikipedia_zh_streaming(target_chunks=100_000)
    except (ImportError, ConnectionError, OSError) as e:
        logger.warning("wikipedia-zh 不可用({}), fallback 合成", e)
        docs = _gen_synthetic_corpus(target_chunks=100_000)
    _build_db(cache, docs)
    return cache
```

- wikipedia: `datasets.load_dataset("wikimedia/wikipedia", "20231101.zh", streaming=True)`，流式取直到估算达 10 万 chunks
- 合成：2000 中文高频词随机拼接
- `.cache/` 加入 `.gitignore`，首次 ~30min，之后秒级

### 基准测试
- `test_p95_under_500ms`：100 query 样本（从语料取高频词组合），统计 P50/P95/P99，断言 P95 < 500ms
- `test_rerank_under_200ms`：rerank=True 场景 P95 < 200ms
- 报告输出到 `tests/perf/.cache/report.json`（附硬件信息）
- 所有 perf 测试挂 `@pytest.mark.perf`，默认 skip，`pytest -m perf` 触发

### Rerank 优化杠杆
- 批量 forward（top_k_candidates=40 一次 forward）
- `torch.inference_mode()`
- fp16 on GPU
- tokenizer `padding="longest"` 减无效计算

## 8. Embedding 吞吐优化（T2.2）

```python
def _auto_batch_size() -> int:
    import torch
    return 64 if torch.cuda.is_available() else 16

class Embedder:
    def __init__(self, batch_size: int | Literal["auto"] = "auto"):
        self.batch_size = _auto_batch_size() if batch_size == "auto" else batch_size
```

- Collection 构造 `Embedder(batch_size=config.embedding.batch_size)`
- 类级模型单例不变；batch_size 为实例级
- 单测 mock `torch.cuda.is_available` 覆盖两分支

## 9. 文档清理清单

**CLAUDE.md**：
- §2.2 LLM 后端表：删除 MVP / 生产阶段区分，统一为 sentence-transformers/transformers
- §2.3 依赖映射：删除 `node-llama-cpp → llama-cpp-python` 行
- §7 差异表：删除 GGUF / logprobs 相关行
- 验收：`git grep "llama[_-]cpp"` 零结果（除本 spec 历史记录）

**docs/design.md**：
- §4.1 `embeddinggemma-300M GGUF` → `Qwen/Qwen3-Embedding-0.6B (sentence-transformers, 1024-dim)`
- §4.1 `Qwen3-Reranker-0.6B GGUF` → `Qwen/Qwen3-Reranker-0.6B (transformers HF checkpoint)`
- §9 yaml sample 同步更新 backend / model_name

## 10. Deferred to M3

记录于 `docs/plans/m3-backlog.md`：

- **Position-aware blending**（CLAUDE.md §5.4）：Rank 1-3: 75% RRF + 25% rerank；4-10: 60/40；11+: 40/60。需真实语料 AB 验证收益。yaml 新增 `retrieval.blending_mode: "pure_rerank" | "position_aware"`
- **Query Expansion**：design.md §7 原评估挪到 M2，现延后 M3；复杂度 vs 收益需真实 query log 验证
- **Strong Signal 跳过扩展**（CLAUDE.md §5.4 BM25 top1>0.85 且 gap>0.15）：依赖 Query Expansion，同批延后

YAGNI 永久放弃（design.md §7）：多进程安全、增量 embedding、多模态、跨 collection 联合检索、权限控制

## 11. DoD

1. 所有 M1 契约测试（89 个）仍全绿
2. 新增批量契约测试（5 个）在 [fake, sqlite] 全绿
3. 新增 rerank 契约测试（2 个）在 `pytest -m reranker` 下全绿（真模型）
4. 新增 config 单测全绿
5. T1.7 smoke 仍绿
6. `pytest -m perf` P95 hybrid_search < 500ms，rerank < 200ms（记录硬件于 report.json）
7. `git grep "llama[_-]cpp"` 零结果（排除 spec 历史）
8. `docs/plans/m3-backlog.md` 提交
9. tag `m2-perf-baseline` 应用

## 12. 风险

| 风险 | 缓解 |
|---|---|
| Qwen3-Reranker HF 下载失败或网络慢 | 本地 huggingface cache 预热；reranker marker 默认 skip |
| wikipedia-zh datasets 不在主依赖 | perf marker 默认 skip，CI 不触发；本地 `pip install -e ".[perf]"` 显式安装 |
| 10 万 chunk 构建耗时 ~30min | 缓存 `.cache/corpus.sqlite`，首次后秒级复用 |
| rerank 200ms 目标 CPU 可能不达标 | baseline 记录 GPU/CPU 两套，CPU 不达标降级 P2 非阻塞 |
| 原子事务大批量内存压力（万级 chunks） | M2 不支持超大批（>1000 docs 建议分批调用）；spec 注释说明 |

## 13. 测试矩阵

| 测试层 | 位置 | 覆盖 | CI 默认 |
|---|---|---|---|
| contract (fake+sqlite) | `tests/contract/` | 原 M1 89 个 + batch 5 个 | ✅ |
| contract (reranker) | `tests/contract/test_rerank.py` | rerank 真模型 2 个 | ❌（marker） |
| unit | `tests/unit/` | config / rerank / embedding | ✅ |
| perf | `tests/perf/` | 10 万 chunk P95 + rerank 延迟 | ❌（marker） |
