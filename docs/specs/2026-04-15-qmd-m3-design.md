# qmd-py M3 Design: Query Expansion + Position-aware Blending + 清理发布

**日期**: 2026-04-15
**范围**: TD.md M3（T3.1–T3.4）+ M2 backlog 全部（Query Expansion / Position-aware Blending / Strong Signal Skip / CPU Rerank 优化）
**分支**: `feat/m3-expansion-blending`（从 `feat/m2-batch-rerank-perf` 切出）
**交付 tag**: `m3-full-pipeline`

## 1. 目标

1. Query Expansion（Qwen3-0.6B instruct）：可选，yaml 可配，生成 lex/vec/hyde 变体扩充检索
2. Position-aware Blending：可选，yaml 可配权重，替代 M2 的 pure_rerank 策略
3. Strong Signal Skip：BM25 top1 强信号时跳过 expansion，节省 ~200ms
4. CPU Rerank 优化：top_k_candidates 减少至 20，CPU 环境可放宽 P95 指标
5. Batch 3x 验证：10 万 chunk 规模验证批量 API 加速比
6. T3.1 清理旧代码：README 最小修复，删 llama-cpp 引用，修正 CLI 示例
7. T3.2 版本号确认
8. T3.4 CHANGELOG.md

## 2. 关键决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | Query Expansion 用 Qwen3-0.6B (instruct)，非 1.7B | 0.6B ~1.2GB 与现有模型同级别，三模型共存 GPU ~3.6GB 可接受 |
| D2 | QueryExpander 类级单例 + 懒加载 | 与 Embedder/Reranker 统一策略，无需 idle timeout（YAGNI） |
| D3 | Expansion 默认关闭（`expansion.enabled: false`） | 每次查询额外 ~200ms，用户按需开启 |
| D4 | 扩展查询多路并行检索 | lex→BM25，vec/hyde→Vector，原查询两路都送且 ×2 权重，忠实 CLAUDE.md §5.4 |
| D5 | Position-aware blending 权重 yaml 可配 | 用户要求可配各档权重，不硬编码 |
| D6 | CPU rerank 优化优先减候选数 | top_k_candidates 40→20，不引入 ONNX/量化额外依赖 |
| D7 | CPU rerank P95 目标可放宽 | 不达 200ms 可调高指标或 xfail，不阻塞发布 |
| D8 | T3.3 私有 PyPI 发布跳过 | 用户确认不需要 |
| D9 | README 最小修复 | 只删错误内容 + 修正 CLI，不完整重写 |

## 3. 完整 Hybrid Search 流程

```
用户查询: "authentication flow"
  ↓
Step 1: BM25 Probe (强信号检测)
  └─ FTS5 查询，取 top1/top2 分数
  └─ 如果 top1_score > 0.85 且 (top1 - top2) > 0.15 → 跳过 Step 2
  ↓
Step 2: Query Expansion (可选，yaml expansion.enabled=true)
  └─ Qwen3-0.6B (instruct) → 生成 3 种变体:
     - lex: 同义词/近义词变体（送 BM25）
     - vec: 语义重述变体（送 Vector）
     - hyde: 假设文档片段（送 Vector）
  ↓
Step 3: 并行检索
  - 原查询 (×2 权重) → BM25 + Vector
  - lex 变体 → BM25
  - vec/hyde 变体 → Vector
  ↓
Step 4: Reciprocal Rank Fusion (RRF)
  - k=60, 合并所有检索结果
  - 取 top-N 候选（N = rerank.top_k_candidates）
  ↓
Step 5: Rerank (可选，rerank=True)
  └─ Qwen3-Reranker-0.6B → yes/no softmax 打分
  ↓
Step 6: Position-aware Blending (可选)
  - pure_rerank: rerank_score 直接排序（M2 行为）
  - position_aware: 按 rank 分档混合 RRF + rerank 分数
    - Rank 1-3:  默认 75% RRF + 25% Rerank
    - Rank 4-10: 默认 60% RRF + 40% Rerank
    - Rank 11+:  默认 40% RRF + 60% Rerank
  ↓
返回 top_k 结果
```

## 4. 文件变更清单

### 新增
- `qmd/core/expansion.py` — `QueryExpander` 类（Qwen3-0.6B 类级单例）
- `tests/unit/test_expansion.py` — QueryExpander mock 单测
- `tests/contract/test_expansion.py` — expansion 集成契约测试（`@pytest.mark.expander`）
- `tests/contract/test_blending.py` — position-aware blending 契约测试
- `CHANGELOG.md` — 版本变更记录

### 修改
- `qmd/core/config.py` — 新增 `ExpansionConfig`、`BlendingWeights`、`RetrievalConfig` 扩展
- `qmd/core/collection.py` — hybrid_search 接入 expansion + blending + strong signal skip
- `qmd/core/retrieval.py` — 多路 RRF 融合支持加权
- `qmd/testing/fakes.py` — FakeCollection 适配 expansion + blending
- `qmd/models.py` — hybrid_search 签名更新（expansion 参数）
- `pyproject.toml` — 版本号、依赖
- `README.md` / `README_CN.md` — 删 llama-cpp 引用，修正 CLI 示例
- `tests/perf/test_hybrid_search_p95.py` — batch 3x 验证测试

## 5. Config Schema 扩展

```yaml
# 新增 expansion section
expansion:
  enabled: false                          # 默认关闭
  model_name: "Qwen/Qwen3-0.6B"
  strong_signal_threshold: 0.85           # BM25 top1 超过此值跳过 expansion
  strong_signal_gap: 0.15                 # top1 - top2 > gap 时跳过

# retrieval section 扩展
retrieval:
  rrf_k: 60
  bm25_top_k: 20
  vector_top_k: 20
  blending_mode: "pure_rerank"            # "pure_rerank" | "position_aware"
  blending_weights:
    top: [0.75, 0.25]                     # rank 1-3: [rrf_weight, rerank_weight]
    mid: [0.60, 0.40]                     # rank 4-10
    tail: [0.40, 0.60]                    # rank 11+
```

**Pydantic schema:**

```python
class BlendingWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    top: tuple[float, float] = (0.75, 0.25)
    mid: tuple[float, float] = (0.60, 0.40)
    tail: tuple[float, float] = (0.40, 0.60)

class ExpansionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    model_name: str = "Qwen/Qwen3-0.6B"
    strong_signal_threshold: float = 0.85
    strong_signal_gap: float = 0.15

class RetrievalConfig(BaseModel):
    # 现有字段 ...
    blending_mode: Literal["pure_rerank", "position_aware"] = "pure_rerank"
    blending_weights: BlendingWeights = BlendingWeights()
```

## 6. QueryExpander 实现

```python
class QueryExpander:
    """Qwen3-0.6B query expansion — 类级单例，懒加载。"""
    MODEL_NAME = "Qwen/Qwen3-0.6B"
    _shared_model = None
    _shared_tokenizer = None
    _shared_lock = threading.Lock()

    def _load(self): ...  # AutoTokenizer + AutoModelForCausalLM, fp16 GPU / fp32 CPU

    def expand(self, query: str) -> dict[str, list[str]]:
        """生成查询变体。返回 {"lex": [...], "vec": [...], "hyde": [...]}。"""
        prompt = _build_expansion_prompt(query)
        output = self._generate(prompt)
        return _parse_expansion_output(output)
```

**Prompt 设计**（让模型输出结构化 JSON）：
```
Given the search query: "{query}"
Generate search query variants in JSON format:
{
  "lex": ["synonym/keyword variant 1", "variant 2"],
  "vec": ["semantic rephrase 1"],
  "hyde": ["hypothetical document snippet"]
}
Output ONLY the JSON, no explanation.
```

**空结果处理**：解析失败或空结果 → 降级为仅用原查询，不抛错。

## 7. Position-aware Blending 实现

```python
def position_aware_blend(
    candidates: list[SearchResult],
    blending_weights: BlendingWeights,
) -> list[SearchResult]:
    """按 rank 分档混合 RRF score 和 rerank score。"""
    for i, c in enumerate(candidates):
        rank = i + 1
        if rank <= 3:
            rrf_w, rerank_w = blending_weights.top
        elif rank <= 10:
            rrf_w, rerank_w = blending_weights.mid
        else:
            rrf_w, rerank_w = blending_weights.tail
        c.score = rrf_w * c.score + rerank_w * c.rerank_score
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
```

**前提**：blending 仅在 `rerank=True` 且 `blending_mode="position_aware"` 时生效。

## 8. Strong Signal Skip 实现

在 `hybrid_search` 内，expansion 前加一步 BM25 probe：

```python
if config.expansion.enabled:
    # BM25 probe: 只取 top-2 检查强信号
    probe_rows = self._bm25_probe(query, limit=2)
    if len(probe_rows) >= 2:
        top1_score, top2_score = probe_rows[0][1], probe_rows[1][1]
        if (top1_score > config.expansion.strong_signal_threshold
            and (top1_score - top2_score) > config.expansion.strong_signal_gap):
            skip_expansion = True
```

**`_bm25_probe`**：轻量 FTS5 查询，只取 rank 分数不做完整检索。

## 9. CPU Rerank 优化

不新增代码。策略：
1. `rerank.top_k_candidates` 已在 yaml 可配（M2 实现），CPU 用户配 20 即可
2. perf 测试中 CPU 环境若 P95>200ms，放宽至 P95<500ms 或标 xfail
3. 文档注明 CPU 推荐配置

## 10. 多路 RRF 融合

当前 `rrf_fuse` 接受 `list[list[int]]`（多个排名列表）。需扩展支持加权：

```python
def rrf_fuse(
    ranked_lists: list[list[int]],
    k: int = 60,
    weights: list[float] | None = None,   # 新增：每个列表的权重
) -> list[tuple[int, float]]:
    """加权 RRF 融合。weights=None 时等权（向后兼容）。"""
```

原查询的 BM25/Vector 列表权重 = 2.0，扩展查询的列表权重 = 1.0。

## 11. 测试策略

| 测试层 | 位置 | 覆盖 | CI 默认 |
|---|---|---|---|
| unit | `tests/unit/test_expansion.py` | QueryExpander mock（解析、空结果降级、prompt 格式） | ✅ |
| unit | `tests/unit/test_config.py` | 新增 expansion/blending config 字段 | ✅ |
| unit | `tests/unit/test_retrieval.py` | 加权 RRF 融合 | ✅ |
| contract (fake+sqlite) | `tests/contract/test_blending.py` | position_aware 排序影响、pure_rerank 不变 | ✅ |
| contract (expander) | `tests/contract/test_expansion.py` | 真模型 expansion→检索（`@pytest.mark.expander`） | ❌（marker） |
| perf | `tests/perf/` | batch 3x 验证、CPU rerank 指标 | ❌（marker） |

## 12. 清理/发布任务

### T3.1 README 最小修复
- 删除 `llama-cpp-python` / GGUF 引用
- CLI 示例改为当前实际命令：`python -m qmd document add/list/get`, `search`, `collection list`
- 安装说明改为 `pip install qmd` + `pip install "qmd[dev]"`

### T3.2 版本号
- 当前 pyproject.toml 已是 `0.1.1`
- 确认保持 0.1.1 或按 TD.md 要求回退 0.1.0（需用户确认）

### T3.4 CHANGELOG
```markdown
# Changelog

## 0.1.0 — 完全重写

qmd-py 0.1.0 是完整重写版本，与旧 API 不兼容。

### 新增
- SQLite + sqlite-vec 混合检索引擎
- Qwen3-Embedding-0.6B 向量编码
- Qwen3-Reranker-0.6B 重排序
- BM25 + Vector + RRF 融合检索
- 批量 add_documents API（原子事务）
- qmd.yaml 配置系统
- Query Expansion（Qwen3-0.6B，可选）
- Position-aware Blending（可选）
- CLI + MCP 接口
```

## 13. DoD

1. 所有 M1/M2 契约测试仍全绿（128 个）
2. 新增 blending 契约测试在 [fake, sqlite] 全绿
3. 新增 expansion 契约测试在 `pytest -m expander` 下全绿（真模型）
4. 新增 config 单测（expansion/blending 字段）全绿
5. 加权 RRF 单测全绿
6. README 无 llama-cpp 引用
7. CHANGELOG.md 提交
8. `pytest -m perf` batch 3x 验证通过（10万 scale）
9. CPU rerank P95 记录（不达 200ms 可放宽/xfail）
10. tag `m3-full-pipeline` 应用

## 14. 风险

| 风险 | 缓解 |
|---|---|
| Qwen3-0.6B 生成质量不稳定（输出非 JSON） | 解析失败降级为仅用原查询，不阻塞检索 |
| 三模型共存 GPU OOM（低显存环境） | 0.6B×3 ~3.6GB，4GB 以下显卡可关 expansion |
| expansion 增加 ~200ms 延迟 | 默认关闭，strong signal skip 减少不必要调用 |
| position_aware blending 效果不如 pure_rerank | yaml 可切换，用户自行 AB 对比 |
| 10万 batch 3x 目标仍不达标 | 记录实际数据，放宽或标注硬件要求 |
