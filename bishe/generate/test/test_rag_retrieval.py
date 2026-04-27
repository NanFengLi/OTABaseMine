#!/usr/bin/env python3
"""简单的 RAG 检索自测脚本。"""

import argparse
import textwrap

from bishe.generate.rag_db import RAGDatabase


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 检索测试脚本")
    parser.add_argument(
        "-q",
        "--query",
        action="append",
        required=True,
        help="查询词，可重复传入，如 -q RRCConnectionReconfiguration -q MeasSubframePattern",
    )
    parser.add_argument("-k", "--topk", type=int, default=3, help="每个查询返回条数")
    parser.add_argument("--hybrid", action="store_true", help="启用混合检索（向量+关键词）")
    parser.add_argument("--rerank", action="store_true", help="启用 rerank（需配置 DASHSCOPE_API_KEY）")
    parser.add_argument("--spec", default=None, help="spec_number 过滤，如 36331")
    parser.add_argument("--version", default=None, help="version 过滤，如 j00")
    parser.add_argument("--message", default=None, help="message_releated 过滤，如 RRCConnectionReconfiguration")
    parser.add_argument("--max-chars", type=int, default=220, help="每条结果展示的最大字符数")

    args = parser.parse_args()

    rag = RAGDatabase()
    if not rag.client:
        print("[ERROR] Milvus 客户端未初始化成功。")
        return 2

    count = rag._collection_count()
    print(f"[INFO] collection_count = {count}")
    if count <= 0:
        print("[WARN] 当前库为空，请先执行: python bishe/generate/main_gen.py -b -f")
        return 1

    for q in args.query:
        results = rag.query_asn1(
            query_texts=[q],
            n_results=args.topk,
            spec_number=args.spec,
            version=args.version,
            message_releated=args.message,
            hybrid=args.hybrid,
            use_rerank=args.rerank,
        )

        print("\n" + "=" * 80)
        print(f"QUERY: {q}")
        print(f"RESULT_COUNT: {len(results)}")

        if not results:
            print("[WARN] 无结果")
            continue

        for i, item in enumerate(results, 1):
            preview = item if len(item) <= args.max_chars else item[: args.max_chars] + "..."
            preview = preview.replace("\n", " ")
            print(textwrap.dedent(f"""
            [{i}]
            {preview}
            """).strip())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
