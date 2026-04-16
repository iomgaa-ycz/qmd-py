# M3 Backlog — 从 M2 延后到 M3 的事项

> 记录 M2 阶段明确延后到 M3 的事项，避免遗忘。M2 阶段的具体决策与理由见 `docs/specs/2026-04-15-qmd-m2-design.md` §10。

## 从 M2 延后

### 1. Position-aware blending（rerank 排序策略优化）

**背景**
M2 采用的排序策略是 "pure rerank"（rerank=True 时完全用 `rerank_score` 替代 RRF 分数）。CLAUDE.md §5.4 与 qmd 原版 TypeScript 采用的是加权混合策略（position-aware blending）。

**方案**
- 在 `qmd.yaml` 新增字段：`retrieval.blending_mode: "pure_rerank" | "position_aware"`
- 权重规则（position_aware）：
  - Rank 1-3: 75% RRF + 25% rerank
  - Rank 4-10: 60% RRF + 40% rerank
  - Rank 11+: 40% RRF + 60% rerank

**理由**
混合策略能缓解 reranker 在 top 位置的过度调整（reranker 对语义细节敏感，但 RRF 反映全局共识）。需要真实语料 AB test 验证 MRR / NDCG 是否有显著提升。

**预估**：1d 实现 + 1d AB test

### 2. Query Expansion

**背景**
design.md §7 原列入 M2 评估，M2 决定继续延后。

**方案**
- 使用轻量 LLM（如 Qwen3-1.7B）生成 query 的 lex/vec/hyde 变体
- 在 hybrid_search 中将扩展 query 也纳入 BM25 / vector 检索，权重合并到 RRF

**收益**
qmd 原版 benchmark 显示召回提升 10-15%。

**代价**
- 每 query 额外 ~200ms LLM 调用（不可忽视）
- 新增一个模型依赖（下载 + 显存）

**决策依据**
需真实 query log 验证收益是否值得 latency 代价。

**预估**：2-3d

### 3. Strong Signal 跳过扩展

**背景**
CLAUDE.md §5.4 — 若 BM25 top1 > 0.85 且 (top1 − top2) gap > 0.15，说明查询词汇已经足够明确，跳过 Query Expansion 节省 ~200ms。

**依赖**
必须先完成 Query Expansion（#2）。

**预估**：0.5d（在 #2 基础上）

### 4. Rerank P95 < 200ms CPU 达标

**背景**
Task 11 perf 测试在 CPU 环境下 rerank P95 可能不达标（xfail 降级记录，不阻塞 M2 DoD）。

**方案**
- fp16 / int8 量化
- 减少 `top_k_candidates`（40 → 20）的影响评估
- 或：改用更小的 reranker 变体

**预估**：1-2d

## YAGNI 永久放弃（design.md §7）

- 多进程安全 / 分布式部署
- 增量 embedding（保持全量 re-embed 策略）
- 多模态（仅 Markdown 文本）
- 跨 collection 联合检索（Scrivai 可以串行多次 search + 合并）
- 权限控制

## M3 原计划任务（TD.md M3）

- **T3.1** 清理旧代码：`git grep -E "create_store|NamedCollection|old_.*"` 零结果
- **T3.2** `pyproject.toml` → version 0.1.0
- **T3.3** 可选：发布到私有 PyPI
- **T3.4** CHANGELOG（标明 0.1.0 是完全重写，不兼容旧 API）
