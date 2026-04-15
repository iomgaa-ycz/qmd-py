"""qmd CLI：JSON-stdout 子命令。

每个子命令的输出对应 Python API 的 model_dump(mode='json')，
保证 CLI 和 Python API 形状一致（契约测试会比对）。

用法：
    qmd search --collection <n> --query <q> [--top-k 5] [--rerank] [--filters '<json>']
    qmd collection info --collection <n>
    qmd collection list
    qmd document get|add|delete|list ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from qmd import connect


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qmd")
    p.add_argument("--db-path", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    # search
    s = sub.add_parser("search")
    s.add_argument("--collection", required=True)
    s.add_argument("--query", required=True)
    s.add_argument("--top-k", type=int, default=5)
    s.add_argument("--rerank", action="store_true")
    s.add_argument("--filters", default=None)

    # collection
    c = sub.add_parser("collection")
    csub = c.add_subparsers(dest="sub", required=True)
    ci = csub.add_parser("info")
    ci.add_argument("--collection", required=True)
    csub.add_parser("list")

    # document
    d = sub.add_parser("document")
    dsub = d.add_subparsers(dest="sub", required=True)
    dg = dsub.add_parser("get")
    dg.add_argument("--collection", required=True)
    dg.add_argument("--document-id", required=True)
    da = dsub.add_parser("add")
    da.add_argument("--collection", required=True)
    da.add_argument("--document-id", required=True)
    da.add_argument("--markdown-file", required=True)
    da.add_argument("--metadata-json", default=None)
    dd = dsub.add_parser("delete")
    dd.add_argument("--collection", required=True)
    dd.add_argument("--document-id", required=True)
    dl = dsub.add_parser("list")
    dl.add_argument("--collection", required=True)

    return p


def _resolve_db_path(args: argparse.Namespace) -> str | None:
    if args.db_path:
        return args.db_path
    env = os.environ.get("QMD_DB_PATH")
    if env:
        return env
    return None  # connect() 用默认


# ---------- 子命令 ----------

def _cmd_search(client, ns) -> list[dict]:
    filters = json.loads(ns.filters) if ns.filters else None
    col = client.collection(ns.collection)
    results = col.hybrid_search(
        ns.query, top_k=ns.top_k, rerank=ns.rerank, filters=filters
    )
    return [r.model_dump(mode="json") for r in results]


def _cmd_collection_info(client, ns) -> dict:
    return client.collection(ns.collection).info().model_dump(mode="json")


def _cmd_collection_list(client, ns=None) -> list[dict]:
    return [info.model_dump(mode="json") for info in client.list_collections()]


def _cmd_document_get(client, ns) -> dict | None:
    return client.collection(ns.collection).get_document(ns.document_id)


def _cmd_document_add(client, ns) -> dict:
    md = Path(ns.markdown_file).read_text(encoding="utf-8")
    metadata: dict[str, Any] = (
        json.loads(ns.metadata_json) if ns.metadata_json else {}
    )
    client.collection(ns.collection).add_document(ns.document_id, md, metadata)
    return {"ok": True, "document_id": ns.document_id}


def _cmd_document_delete(client, ns) -> dict:
    client.collection(ns.collection).delete_document(ns.document_id)
    return {"ok": True, "document_id": ns.document_id}


def _cmd_document_list(client, ns) -> list[str]:
    return client.collection(ns.collection).list_documents()


def _dispatch(client, ns: argparse.Namespace) -> Any:
    if ns.cmd == "search":
        return _cmd_search(client, ns)
    if ns.cmd == "collection":
        if ns.sub == "info":
            return _cmd_collection_info(client, ns)
        if ns.sub == "list":
            return _cmd_collection_list(client, ns)
    if ns.cmd == "document":
        return {
            "get": _cmd_document_get,
            "add": _cmd_document_add,
            "delete": _cmd_document_delete,
            "list": _cmd_document_list,
        }[ns.sub](client, ns)
    raise ValueError(f"未知命令: {ns.cmd}")


def main(argv: list[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    client = None
    try:
        client = connect(_resolve_db_path(ns))
        result = _dispatch(client, ns)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001 — CLI 顶层兜底
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
