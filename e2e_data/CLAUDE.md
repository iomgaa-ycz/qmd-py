# CLAUDE — ycz-database 仓库管理与维护指南（正式版）

> 目标：让余承璋在 Obsidian 里写得轻松；让婷婷负责提纯与维护知识库。
> 
> 一句话原则：**写入 Inbox，提纯进 Notes；每条 Notes 必须有唯一归属 owner；Project/Area 通过 Bases 自动索引。**

---

## 0) 三个入口（永远从这里开始）
- `Home.md`：总入口（导航 + 当前活跃）
- `Inbox/Inbox.md`：碎片收件箱（Capture 入口）
- `Tasks.md`：任务仪表盘（Tasks 插件聚合）

---

## 1) 文件夹与角色分工（结构规则）
> 这个库的设计是：**Notes 是知识本体，Projects/Areas 是地图层。**

- `Notes/`：资源/知识本体（论文笔记、概念、方案、会议纪要、教程、随想等）
- `Projects/`：项目主页（目标、里程碑、任务、关键入口；通过自动索引聚合所属 Notes）
- `Areas/`：领域主页（地图/综述/导航；只放指针，不复制内容；通过自动索引聚合所属 Notes）
- `Inbox/`：临时收件箱（允许脏，必须被处理）
- `Calendar/`：日记与日任务（YYYY-MM-DD）
- `Archive/`：冷冻与历史（不再活跃但要保留的内容；含迁移备份）
- `template/`：模板（新建 Project/Area/Note 时必须用模板，防止跑偏）
- `access/`：附件（图片、PDF、截图、视频等）

---

## 2) 归属唯一（强规则）
**任何内容型笔记（放在 `Notes/`）必须且只能属于一个：Project 或 Area（二选一）。**

落地方式（强制执行）：
- 每篇 `Notes/*.md` 顶部必须有 YAML：
  - `owner: project/<项目名>` 或
  - `owner: area/<领域名>`

说明：
- **长期知识默认归 Project**（余承璋已确认）：项目产出的可复用内容算项目资产。
- **Area 只做地图层**：允许在 Area 里只放链接指针与导航结构，不复制内容。

---

## 3) 自动索引（强规则，取代手工反向链接）
> 只要 Notes 写对 owner，Project/Area 就应自动出现它。

### 3.1 Project/Area 的 ownerKey
每个 Project/Area 页面（`Projects/*.md`、`Areas/*.md`）必须在 frontmatter 里有：
- Project：`ownerKey: "project/<本页标题>"`
- Area：`ownerKey: "area/<本页标题>"`

### 3.2 Bases 自动索引块
每个 Project/Area 页面必须包含以下 Bases 块（或等价实现）：

```base
filters:
  and:
    - file.inFolder("Notes")
    - note.owner == this.ownerKey
views:
  - type: table
    name: Notes
```

效果：
- 新增一条 Notes，只要加了 `owner`，对应 Project/Area 会自动索引到。
- 不再手工维护“反向链接清单”（除非是“关键入口（手选）”的小列表）。

---

## 4) Capture → Distill（工作流）

### 4.1 Capture（余承璋做）
- 随手写、允许脏：一律写入 `Inbox/`。
- 最低要求：不要 Untitled；至少一句话说明“这条在讲什么”。

### 4.2 Distill（婷婷做）
建议频率：每周一次或积累到 20 条。
- 选归属：Project / Area / Calendar
- 重命名（可检索、可复用的标题）
- 将内容放入 `Notes/`（必要时从 Inbox 移过去）
- 补齐 `owner`（唯一归属）
- 补最小标签（可选，遵循标签规则）
- 必要时把碎片升格为结构化条目（例如拆分、合并、提炼段落）

---

## 5) 任务系统（强规则）
任务只允许出现于：
1) `Calendar/YYYY-MM-DD.md`（日任务）
2) `Projects/*.md`（项目任务）

### 5.1 任务的“可聚合”格式约定（重要）
> 我们约定 **以 scheduled 为主**（而不是 due）。
>
> 额外强规则：**同一条任务不要同时出现在 Calendar 和 Project**。
> - 原因：避免你需要在两个地方重复勾选完成，且防止 Tasks 聚合重复/状态不一致。
> - 落地：
>   - 如果任务是“项目推进事项”→ 写在 `Projects/<项目>.md`
>   - 如果任务是“当天个人待办/杂事”→ 写在 `Calendar/YYYY-MM-DD.md`
>   - 禁止在 Calendar（尤其是“今日待办”）里添加**不带 checkbox 的提醒**。需要查看所有项目任务时，统一通过 `Tasks.md` 聚合检索。

- 每条任务必须是标准 Markdown checkbox：
  - `- [ ] ...` / `- [x] ...`
- **Calendar（日记）里的每条任务必须带 scheduled 日期**（否则 Tasks 插件查询可能聚合不到我们想看的“Today/Next7days”）：
  - 例：`- [ ] 检查 train_router.py 运行结果 ⏳ 2026-01-14`
- Project 里的任务可不强制日期，但若需要进入时间视图，也应补：
  - `⏳ YYYY-MM-DD`

### 5.2 Tasks.md 的查询约定
- Today：用 `scheduled today`
- Next 7 days：用 `scheduled after today` + `scheduled before tomorrow + 7 days`

然后用 Tasks 插件在 `Tasks.md` 聚合：
- 不再在 `Notes/`、`Areas/`、`Inbox/`、`Archive/` 里散落任务清单。

---

## 6) 命名与标签（弱规则，但建议遵守）
### 6.1 命名
- Project 名：优先英文驼峰或清晰中文全称（保持稳定，避免频繁改名）
- Area 名：中文为主（如“强化学习”），必要时英文（如“LLM”）

### 6.2 标签（允许中英混用，但要有秩序）
- 领域/学科：中文（如 `强化学习`）
- 项目/系统：英文驼峰（如 `TradeSwarm`、`ClaudeCode`）
- 形态/流程：少量固定小写（如 `inbox`、`note`、`paper`、`idea`）

---

## 7) 大改动前的确认原则
- 批量移动/重命名/归档：先给余承璋预览影响范围，再执行。
- 单篇提纯：可直接执行，但要在周总结/变更记录里汇报。

---

## 8) 本次整理（2026-01-27）沉淀的经验
- **目录名必须表达语义**：`Notes/` 比 `note/` 更能避免误解与漂移。
- **“唯一归属”必须机器可读**：用 `owner` 字段比纯链接更可靠。
- **地图页要自动化**：用 Bases 让索引随 owner 自动更新，降低维护成本。
- **兜底分类要明确**：Meta/Personal 这类兜底 Area 能避免“无处安放”的笔记污染核心结构。

