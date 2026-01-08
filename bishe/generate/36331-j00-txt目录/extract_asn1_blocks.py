#!/usr/bin/env python3
"""Extract every ASN.1 block delimited by '-- ASN1START' and '-- ASN1STOP'.

For each block we look at the last non-empty line immediately before the
'-- ASN1START' marker and use that text as the output file name
(e.g. "TDD-Config information element" -> "TDD-Config information element.txt").
The file content contains everything between the start/stop markers (markers
excluded).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List


def parse_args() -> argparse.Namespace:
    """解析命令行参数，允许指定源文件与输出目录。"""
    parser = argparse.ArgumentParser(description="Extract ASN.1 sections into standalone text files")
    parser.add_argument("source", nargs="?", default="36331-j00-修改乱码-删除无关block-删除SetupRelease-补充元素类型.txt", help="Input text file with ASN.1 sections")
    parser.add_argument("--out", default="asn1_sections", dest="out_dir", help="Directory to place extracted files")
    return parser.parse_args()


def load_lines(path: str) -> List[str]:
    """读取文本内容并在出错时立即终止。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.readlines()
    except OSError as exc:
        raise SystemExit(f"Failed to read {path}: {exc}")


def find_header(lines: List[str], start_index: int) -> str:
    """回溯 -- ASN1START 之前的非空行，作为文件名来源。"""
    idx = start_index - 1
    while idx >= 0:
        candidate = lines[idx].strip()
        if candidate:
            return candidate
        idx -= 1
    return f"section_{start_index}"


def sanitize_header(header: str, collisions: dict[str, int]) -> str:
    """清洗标题文本并为重复标题追加序号，生成安全文件名。"""
    cleaned = re.sub(r"\s+", " ", header).strip()
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "_" for ch in cleaned)
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", cleaned)
    if not cleaned:
        cleaned = "section"
    count = collisions.get(cleaned, 0)
    collisions[cleaned] = count + 1
    if count:
        cleaned = f"{cleaned}_{count}"
    return f"{cleaned}.txt"


def extract_blocks(lines: List[str]) -> List[tuple[str, str]]:
    """扫描所有 ASN.1 片段并返回 (文件名, 正文) 列表。"""
    blocks: List[tuple[str, str]] = []
    collisions: dict[str, int] = {}
    i = 0
    total_lines = len(lines)
    while i < total_lines:
        line = lines[i].strip()
        if line == "-- ASN1START":
            header = find_header(lines, i)
            j = i + 1
            body: List[str] = []
            while j < total_lines and lines[j].strip() != "-- ASN1STOP":
                body.append(lines[j])
                j += 1
            if j == total_lines:
                print(f"Warning: '-- ASN1STOP' missing for header '{header}', skipping", file=sys.stderr)
                break
            content = "".join(body).rstrip() + "\n"
            filename = sanitize_header(header, collisions)
            blocks.append((filename, content))
            i = j  # 跳过已经处理完的块
        i += 1
    return blocks


def write_blocks(blocks: List[tuple[str, str]], out_dir: str) -> None:
    """创建输出目录并逐个写出提取的片段。"""
    os.makedirs(out_dir, exist_ok=True)
    for filename, content in blocks:
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def main() -> None:
    """程序入口：读取源文件、提取片段并写入磁盘。"""
    args = parse_args()
    lines = load_lines(args.source)
    blocks = extract_blocks(lines)
    if not blocks:
        raise SystemExit("No ASN.1 blocks were found.")
    write_blocks(blocks, args.out_dir)
    print(f"Extracted {len(blocks)} blocks into '{args.out_dir}'.")


if __name__ == "__main__":
    main()
