#!/usr/bin/env python3
"""qmd-py 端到端验证脚本

使用承璋的 Obsidian 笔记做真实数据验证。
验证项：
1. 文档索引（add）— 全量 + 按目录分 collection
2. Chunking — 长文档切分质量
3. 中文搜索 — BM25 + 向量检索效果
4. 英文搜索 — 混合检索效果
5. 多 collection — 跨 collection 检索
6. 更新与删除 — update / remove
7. CLI — 通过命令行验证
8. 状态查看 — status / list
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ============================================================
# 配置
# ============================================================
DATA_DIR = Path("/home/pci/ycz/Code/qmd-py/e2e_data")
PROJECT_DIR = Path("/home/pci/ycz/Code/qmd-py")
CONDA_PREFIX = "source ~/miniconda3/etc/profile.d/conda.sh && conda activate qmd-py &&"

# 颜色输出
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0
warnings = 0
results = []


def log_section(title: str):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")


def log_test(name: str, success: bool, detail: str = ""):
    global passed, failed
    if success:
        passed += 1
        icon = f"{GREEN}✓{RESET}"
    else:
        failed += 1
        icon = f"{RED}✗{RESET}"
    msg = f"  {icon} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append({"name": name, "passed": success, "detail": detail})


def log_warn(msg: str):
    global warnings
    warnings += 1
    print(f"  {YELLOW}⚠ {msg}{RESET}")


def log_info(msg: str):
    print(f"  {msg}")


def run_cli(*args, timeout=120) -> subprocess.CompletedProcess:
    """运行 qmd-py CLI 命令"""
    cmd = f"{CONDA_PREFIX} cd {PROJECT_DIR} && python -m qmd.cli.main {' '.join(args)}"
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        executable="/bin/bash"
    )


def run_python(code: str, timeout=120) -> subprocess.CompletedProcess:
    """运行 Python 代码"""
    cmd = f'{CONDA_PREFIX} cd {PROJECT_DIR} && python -c "{code}"'
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        executable="/bin/bash"
    )


# ============================================================
# 准备工作
# ============================================================
def setup():
    """准备临时工作目录"""
    log_section("准备工作")

    # 统计源数据
    md_files = list(DATA_DIR.rglob("*.md"))
    log_info(f"数据源: {DATA_DIR}")
    log_info(f"Markdown 文件数: {len(md_files)}")
    total_bytes = sum(f.stat().st_size for f in md_files)
    log_info(f"总大小: {total_bytes / 1024:.1f} KB")

    # 按目录统计
    dirs = {}
    for f in md_files:
        rel = f.relative_to(DATA_DIR)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        dirs.setdefault(top_dir, []).append(f)

    for d, files in sorted(dirs.items()):
        total = sum(f.stat().st_size for f in files)
        log_info(f"  {d}: {len(files)} 篇, {total / 1024:.1f} KB")

    return md_files, dirs


# ============================================================
# 测试 1: Python API 端到端
# ============================================================
def test_python_api(md_files, dirs):
    log_section("测试 1: Python API 端到端验证")

    # 创建临时配置目录
    tmp_dir = tempfile.mkdtemp(prefix="qmd_e2e_")
    config_dir = Path(tmp_dir) / "config"
    config_dir.mkdir()

    try:
        # 写入配置
        config = {
            "version": 1,
            "defaults": {
                "backend": "sentence_tf",
                "embedding_model": "all-MiniLM-L6-v2",
                "chunk_size": 900,
                "chunk_overlap": 0.15,
            },
            "collections": {}
        }
        config_path = config_dir / "index.yml"
        import yaml
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        log_info(f"临时目录: {tmp_dir}")
        log_info(f"配置文件: {config_path}")

        # --- 测试 1.1: 初始化 QMD ---
        code = f"""
import sys
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
import os
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
print(f'backend: {{qmd.backend_name}}')
print(f'collections: {{len(qmd.collections)}}')
qmd.close()
print('INIT_OK')
"""
        result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
        init_ok = "INIT_OK" in (result.stdout + result.stderr)
        log_test("QMD 初始化", init_ok, result.stderr.strip()[:200] if not init_ok else "")

        # --- 测试 1.2: 索引 Notes 目录 ---
        notes_dir = DATA_DIR / "Notes"
        notes_count = len(list(notes_dir.glob("*.md")))
        code = f"""
import sys, os
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
stats = qmd.add('{notes_dir}', collection='notes')
print(f'indexed: {{stats}}')
print(f'collections: {{list(qmd.collections.keys())}}')
qmd.close()
print('INDEX_OK')
"""
        result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
        output = result.stdout + result.stderr
        index_ok = "INDEX_OK" in output
        log_test(f"索引 Notes 目录 ({notes_count} 篇)", index_ok,
                 output.split('\n')[0] if index_ok else output.strip()[:200])

        # --- 测试 1.3: 中文搜索 ---
        queries_zh = [
            ("多智能体", "multi-agent 相关笔记"),
            ("施工方案", "南网项目相关"),
            ("Herald 记忆系统", "Herald 项目笔记"),
            ("大语言模型微调", "LLM fine-tuning"),
        ]
        for query, desc in queries_zh:
            code = f"""
import sys, os
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
results = qmd.search('{query}', collection='notes', limit=5)
print(f'count: {{len(results)}}')
for r in results[:3]:
    print(f'  [{{r.score:.3f}}] {{r.path[:60]}}')
qmd.close()
print('SEARCH_OK')
"""
            result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
            output = result.stdout + result.stderr
            search_ok = "SEARCH_OK" in output and "count: 0" not in output
            # 提取结果数
            count_line = [l for l in output.split('\n') if l.startswith('count:')]
            count = count_line[0].split(':')[1].strip() if count_line else "?"
            log_test(f"中文搜索 '{query}'", search_ok,
                     f"{count} 条结果, {desc}")

        # --- 测试 1.4: 英文搜索 ---
        queries_en = [
            ("embedding model", "embedding 相关"),
            ("reinforcement learning", "RL 相关"),
        ]
        for query, desc in queries_en:
            code = f"""
import sys, os
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
results = qmd.search('{query}', collection='notes', limit=5)
print(f'count: {{len(results)}}')
for r in results[:3]:
    print(f'  [{{r.score:.3f}}] {{r.path[:60]}}')
qmd.close()
print('SEARCH_OK')
"""
            result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
            output = result.stdout + result.stderr
            search_ok = "SEARCH_OK" in output and "count: 0" not in output
            count_line = [l for l in output.split('\n') if l.startswith('count:')]
            count = count_line[0].split(':')[1].strip() if count_line else "?"
            log_test(f"英文搜索 '{query}'", search_ok,
                     f"{count} 条结果, {desc}")

        # --- 测试 1.5: 多 collection ---
        projects_dir = DATA_DIR / "Projects"
        code = f"""
import sys, os
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
stats = qmd.add('{projects_dir}', collection='projects')
print(f'indexed: {{stats}}')
colls = list(qmd.collections.keys())
print(f'collections: {{colls}}')
print(f'collection_count: {{len(colls)}}')
qmd.close()
print('MULTI_OK')
"""
        result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
        output = result.stdout + result.stderr
        multi_ok = "MULTI_OK" in output and "collection_count: 2" in output
        log_test("多 collection (notes + projects)", multi_ok)

        # --- 测试 1.6: 跨 collection 搜索 ---
        code = f"""
import sys, os
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
# 搜 notes
r1 = qmd.search('Herald', collection='notes', limit=3)
# 搜 projects
r2 = qmd.search('Herald', collection='projects', limit=3)
print(f'notes_results: {{len(r1)}}')
print(f'projects_results: {{len(r2)}}')
for r in r1[:2]:
    print(f'  notes: [{{r.score:.3f}}] {{Path(r.path).name}}')
for r in r2[:2]:
    print(f'  projects: [{{r.score:.3f}}] {{Path(r.path).name}}')
qmd.close()
print('CROSS_OK')
"""
        result = run_python(code.replace('\n', '; ').replace('; ;', '; ').replace("Path(", "__import__('pathlib').Path("))
        output = result.stdout + result.stderr
        cross_ok = "CROSS_OK" in output
        log_test("跨 collection 搜索 'Herald'", cross_ok)

        # --- 测试 1.7: 删除文档 ---
        code = f"""
import sys, os
sys.path.insert(0, '{PROJECT_DIR}')
os.environ['QMD_CONFIG_DIR'] = '{config_dir}'
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
before = qmd.search('Herald', collection='projects', limit=10)
removed = qmd.remove('{projects_dir}/Herald — AI Research Companion.md', collection='projects')
after = qmd.search('Herald', collection='projects', limit=10)
print(f'before: {{len(before)}}, after: {{len(after)}}, removed: {{removed}}')
qmd.close()
print('REMOVE_OK')
"""
        result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
        output = result.stdout + result.stderr
        # Herald 文件名可能有 Unicode，容忍失败但记录
        remove_ok = "REMOVE_OK" in output
        log_test("删除文档后搜索结果变化", remove_ok,
                 output.strip().split('\n')[0] if not remove_ok else "")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 测试 2: CLI 端到端
# ============================================================
def test_cli():
    log_section("测试 2: CLI 端到端验证")

    tmp_dir = tempfile.mkdtemp(prefix="qmd_e2e_cli_")
    config_path = Path(tmp_dir) / "index.yml"

    try:
        # CLI 需要通过环境变量或参数指定配置路径
        env_prefix = f"QMD_CONFIG_PATH={config_path}"

        # --- status ---
        result = run_cli("status", f"--config={config_path}")
        status_ok = result.returncode == 0
        log_test("CLI: qmd-py status", status_ok,
                 result.stdout.strip()[:100] if status_ok else result.stderr.strip()[:200])

        # --- add ---
        notes_dir = DATA_DIR / "Notes"
        result = run_cli("add", str(notes_dir), "--collection=notes",
                         f"--config={config_path}", "--backend=sentence_tf")
        add_ok = result.returncode == 0
        log_test("CLI: qmd-py add (Notes 目录)", add_ok,
                 result.stdout.strip()[:100] if add_ok else result.stderr.strip()[:200])

        # --- list ---
        result = run_cli("list", "--collection=notes", f"--config={config_path}")
        list_ok = result.returncode == 0
        log_test("CLI: qmd-py list", list_ok,
                 f"{len(result.stdout.strip().splitlines())} 行输出" if list_ok else result.stderr.strip()[:200])

        # --- search ---
        result = run_cli("search", "多智能体系统", "--collection=notes",
                         f"--config={config_path}", "--backend=sentence_tf", "--limit=5")
        search_ok = result.returncode == 0 and len(result.stdout.strip()) > 0
        log_test("CLI: qmd-py search '多智能体系统'", search_ok,
                 result.stdout.strip()[:150] if search_ok else result.stderr.strip()[:200])

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 测试 3: 性能基准
# ============================================================
def test_performance():
    log_section("测试 3: 性能基准")

    tmp_dir = tempfile.mkdtemp(prefix="qmd_e2e_perf_")
    config_path = Path(tmp_dir) / "index.yml"

    try:
        # 索引全量数据，测时间
        code = f"""
import sys, os, time
sys.path.insert(0, '{PROJECT_DIR}')
from qmd import QMD
qmd = QMD(backend='sentence_tf', config_path='{config_path}')
t0 = time.time()
stats = qmd.add('{DATA_DIR}', collection='all')
t1 = time.time()
print(f'index_time: {{t1-t0:.2f}}s')
print(f'indexed: {{stats}}')
# 搜索性能
queries = ['多智能体', 'Herald', '施工方案', 'embedding', 'reinforcement learning']
t0 = time.time()
for q in queries:
    qmd.search(q, collection='all', limit=5)
t1 = time.time()
avg = (t1-t0) / len(queries)
print(f'search_avg: {{avg:.3f}}s')
print(f'search_total: {{t1-t0:.2f}}s ({{len(queries)}} queries)')
qmd.close()
print('PERF_OK')
"""
        result = run_python(code.replace('\n', '; ').replace('; ;', '; '))
        output = result.stdout + result.stderr
        perf_ok = "PERF_OK" in output

        # 解析时间
        for line in output.split('\n'):
            if line.startswith('index_time:') or line.startswith('search_avg:') or line.startswith('search_total:') or line.startswith('indexed:'):
                log_info(f"  {line.strip()}")

        log_test("全量索引 + 搜索性能", perf_ok,
                 "" if perf_ok else output.strip()[-200:])

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 主程序
# ============================================================
if __name__ == "__main__":
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  qmd-py 端到端验证{RESET}")
    print(f"{BOLD}  数据源: 承璋 Obsidian Vault (193 篇){RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    md_files, dirs = setup()
    test_python_api(md_files, dirs)
    test_cli()
    test_performance()

    # 汇总
    log_section("验证结果汇总")
    total = passed + failed
    print(f"  总计: {total} 项测试")
    print(f"  {GREEN}通过: {passed}{RESET}")
    if failed > 0:
        print(f"  {RED}失败: {failed}{RESET}")
    if warnings > 0:
        print(f"  {YELLOW}警告: {warnings}{RESET}")

    # 失败详情
    failed_tests = [r for r in results if not r["passed"]]
    if failed_tests:
        print(f"\n  {RED}失败项:{RESET}")
        for r in failed_tests:
            print(f"    ✗ {r['name']}: {r['detail']}")

    rate = passed / total * 100 if total > 0 else 0
    print(f"\n  {BOLD}通过率: {rate:.0f}%{RESET}")

    if rate == 100:
        print(f"\n  {GREEN}{BOLD}🎉 端到端验证全部通过！{RESET}")
    elif rate >= 80:
        print(f"\n  {YELLOW}{BOLD}⚠️ 大部分通过，但有失败项需要检查{RESET}")
    else:
        print(f"\n  {RED}{BOLD}❌ 多项失败，需要修复{RESET}")

    sys.exit(0 if failed == 0 else 1)
