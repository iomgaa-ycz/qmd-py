#!/usr/bin/env python3
"""qmd-py 端到端验证 — 承璋 Obsidian Vault (193 篇)

API 参考:
- QMD(backend, config_path)
- qmd.add(name, path, pattern)  — 注册 collection
- qmd.update(name)              — 执行索引
- qmd.search(query, collections=[...], limit)  — 搜索
- qmd.remove(name)              — 删除 collection
- qmd.collections               — list[NamedCollection]
- SearchResult: file, title, body, score, collection, hash, pos
- chunk_document(content, max_chars, overlap_chars, window_chars) -> list[Chunk]
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = Path("/home/pci/ycz/Code/qmd-py")
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR = Path("/home/pci/ycz/Code/qmd-py/e2e_data")

G = "\033[92m"
R = "\033[91m"
B = "\033[94m"
BD = "\033[1m"
RS = "\033[0m"

passed = 0
failed = 0
results = []


def section(t):
    print(f"\n{BD}{B}{'='*60}\n  {t}\n{'='*60}{RS}\n")


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    icon = f"{G}✓{RS}" if ok else f"{R}✗{RS}"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    results.append({"name": name, "ok": ok, "detail": detail})


def info(msg):
    print(f"  {msg}")


# ============================================================
section("准备工作")
md_files = sorted(DATA_DIR.rglob("*.md"))
info(f"数据源: {DATA_DIR}")
info(f"Markdown 文件: {len(md_files)} 篇, {sum(f.stat().st_size for f in md_files)/1024:.1f} KB")
check("数据源非空", len(md_files) > 50, f"{len(md_files)} 篇")

tmp_dir = tempfile.mkdtemp(prefix="qmd_e2e_")
info(f"临时目录: {tmp_dir}")

try:
    from qmd import QMD
    from qmd.core.chunking import chunk_document

    # ============================================================
    section("测试 1: Chunking 质量")

    long_files = sorted(md_files, key=lambda f: f.stat().st_size, reverse=True)[:3]
    for lf in long_files:
        info(f"大文件: {lf.name} ({lf.stat().st_size/1024:.1f} KB)")

    content = long_files[0].read_text(encoding="utf-8", errors="replace")
    chunks = chunk_document(content)
    total_ch = sum(len(c.text) for c in chunks)
    sizes = [len(c.text) for c in chunks]

    check("Chunking 产出非空", len(chunks) > 0, f"{len(chunks)} chunks")
    check("内容保留 >=80%", total_ch >= len(content) * 0.8,
          f"原文 {len(content)} 字 → chunks {total_ch} 字")
    check("Chunk 大小合理", sum(sizes)/len(sizes) < 5000,
          f"avg={sum(sizes)/len(sizes):.0f}, min={min(sizes)}, max={max(sizes)}")

    # ============================================================
    section("测试 2: 索引 Notes")

    cfg1 = str(Path(tmp_dir) / "cfg1.yml")
    qmd = QMD(backend="sentence_tf", config_path=cfg1)

    notes_dir = DATA_DIR / "Notes"
    n_notes = len(list(notes_dir.glob("*.md")))
    info(f"Notes: {n_notes} 篇")

    qmd.add("notes", str(notes_dir))
    t0 = time.time()
    stats = qmd.update("notes")
    t_idx = time.time() - t0

    indexed = stats.get("indexed", 0) + stats.get("updated", 0)
    info(f"索引: {indexed} 篇, {t_idx:.1f}s")
    check("Notes 索引成功", indexed > 0, f"{indexed} 篇, {t_idx:.1f}s")
    check("索引耗时 <180s", t_idx < 180, f"{t_idx:.1f}s")

    # ============================================================
    section("测试 3: 中文搜索")

    for q in ["多智能体", "施工方案", "大语言模型", "记忆系统", "代码生成"]:
        t0 = time.time()
        res = qmd.search(q, collections=["notes"], limit=5)
        dt = (time.time() - t0) * 1000
        if res:
            r = res[0]
            check(f"中文 '{q}'", True,
                  f"{len(res)} 条, top=[{r.score:.3f}] {Path(r.file).name}, {dt:.0f}ms")
        else:
            check(f"中文 '{q}'", False, f"0 条, {dt:.0f}ms")

    # ============================================================
    section("测试 4: 英文搜索")

    for q in ["embedding model", "reinforcement learning", "transformer architecture"]:
        t0 = time.time()
        res = qmd.search(q, collections=["notes"], limit=5)
        dt = (time.time() - t0) * 1000
        if res:
            r = res[0]
            check(f"英文 '{q}'", True,
                  f"{len(res)} 条, top=[{r.score:.3f}] {Path(r.file).name}, {dt:.0f}ms")
        else:
            check(f"英文 '{q}'", False, f"0 条, {dt:.0f}ms")

    # ============================================================
    section("测试 5: 多 Collection")

    for name, path in [("projects", DATA_DIR/"Projects"), ("areas", DATA_DIR/"Areas")]:
        if path.exists():
            qmd.add(name, str(path))
            qmd.update(name)

    coll_names = [c.name for c in qmd.collections]
    check("3 个 collection", len(coll_names) >= 3, str(coll_names))

    r1 = qmd.search("Herald", collections=["notes"], limit=3)
    r2 = qmd.search("Herald", collections=["projects"], limit=3)
    check("Notes 搜 Herald", len(r1) > 0, f"{len(r1)} 条")
    check("Projects 搜 Herald", len(r2) > 0, f"{len(r2)} 条")

    # ============================================================
    section("测试 6: 删除 Collection")

    before = [c.name for c in qmd.collections]
    qmd.remove("areas")
    after = [c.name for c in qmd.collections]
    check("删除 areas", "areas" not in after, f"{before} → {after}")

    qmd.stop()

    # ============================================================
    section("测试 7: 性能基准 — 全量索引")

    cfg2 = str(Path(tmp_dir) / "cfg2.yml")
    qp = QMD(backend="sentence_tf", config_path=cfg2)
    qp.add("all", str(DATA_DIR))

    t0 = time.time()
    ps = qp.update("all")
    t_full = time.time() - t0
    p_idx = ps.get("indexed", 0) + ps.get("updated", 0)
    info(f"全量: {p_idx} 篇, {t_full:.1f}s" + (f", {t_full/p_idx*1000:.0f}ms/篇" if p_idx else ""))
    check("全量索引", p_idx > 0, f"{p_idx} 篇, {t_full:.1f}s")

    queries = ["多智能体", "Herald", "施工方案", "embedding", "transformer",
               "代码生成", "记忆", "论文写作"]
    t0 = time.time()
    for q in queries:
        qp.search(q, collections=["all"], limit=5)
    t_search = time.time() - t0
    avg_ms = t_search / len(queries) * 1000
    info(f"搜索: {len(queries)} 次, 总 {t_search:.2f}s, avg {avg_ms:.0f}ms")
    check("搜索延迟 <2s", avg_ms < 2000, f"avg={avg_ms:.0f}ms")

    qp.stop()

finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)

# ============================================================
section("结果汇总")
total = passed + failed
print(f"  总计: {total} 项")
print(f"  {G}通过: {passed}{RS}")
if failed:
    print(f"  {R}失败: {failed}{RS}")
    for r in results:
        if not r["ok"]:
            print(f"    ✗ {r['name']}: {r['detail']}")
rate = passed / total * 100 if total else 0
print(f"\n  {BD}通过率: {rate:.0f}%{RS}")
if rate == 100:
    print(f"\n  {G}{BD}🎉 端到端验证全部通过！{RS}")
sys.exit(0 if failed == 0 else 1)
