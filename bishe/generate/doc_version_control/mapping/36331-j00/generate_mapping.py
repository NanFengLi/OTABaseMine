from __future__ import annotations

"""生成 extracted/*.asn 与 asn1_blocks/*.txt 的对应关系（mapping.json）。

本脚本用于回答：某个 extracted 目录下的 .asn 文件里，实际“用到了”哪些 asn1_blocks 里的定义。

为什么不能只靠文件名？
- extracted/*.asn 里出现的定义通常来自多个 block 文件；
- block 文件里的定义在 .asn 中可能是“分散出现”的（中间插入其它定义），
    因此不能用“整段文本必须连续包含”的方式判断。

因此默认采用 `defs` 模式：
- 把每个 asn1_blocks/*.txt 按 `Name ::= ...` 切成若干“定义块”；
- 如果某个 .asn（规范化空白后）包含该 .txt 中任意一个定义块，则认为该 .txt 被使用。

也保留了两个调试/对比模式：
- content：整段 .txt 规范化后必须作为连续子串出现在 .asn 中（严格，容易漏匹配）
- name：按标识符/类型名 token 与（去后缀后的）文件名进行匹配（宽松，可能误匹配）
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Block:
    path: str
    canonical_text: str


def canonicalize(text: str) -> str:
    """把 ASN.1 文本做“空白规范化”，提升匹配稳定性。

    现实中 extracted/.asn 与 asn1_blocks/.txt 常见差异：
    - tab vs 空格
    - 不同缩进
    - 不同换行

    我们把所有空白（空格/制表符/换行等）压缩为单个空格，
    从而让“内容包含”判断不受排版影响。
    """

    # 去掉 BOM（有些文本会带），并将所有空白压缩成单空格。
    text = text.replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


ASN_DEF_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*::=", re.MULTILINE)


def extract_definition_blocks(text: str) -> list[str]:
    """按 `Name ::= ...` 把文件切分成多个 ASN.1 定义块。

    定义块范围：从某个 `Name ::=` 行开始，到下一个 `X ::=` 行之前（或文件末尾）。
    这样可以处理“同一个 .txt 里有多个定义”的情况。
    """

    matches = list(ASN_DEF_RE.finditer(text))
    if not matches:
        return []

    blocks: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            blocks.append(chunk)
    return blocks


# 下面这一段是“按名字/token 匹配”的旧逻辑：保留用于对比/调试。
# 原理：把 asn1_blocks 的文件名（去掉 message / information element(s) 后缀）当作类型名，
# 在 .asn 中提取所有 token，命中则认为使用了该文件。
SUFFIXES = (
    " information elements",
    " information element",
    " message",
)


def normalize_block_name(name: str) -> str:
    """把 block 文件名（不含扩展名）规范化为类型/消息名。

    例如：
    - "CounterCheck message" -> "CounterCheck"
    - "DRB-Identity information elements" -> "DRB-Identity"
    """
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def build_block_index(blocks_dir: Path, root: Path) -> dict[str, str]:
    """构建 {类型名: block相对路径} 的索引（用于 name 模式）。"""
    index: dict[str, str] = {}
    for path in blocks_dir.glob("*.txt"):
        base = normalize_block_name(path.stem)
        index.setdefault(base, path.relative_to(root).as_posix())
    return index


def collect_tokens(text: str) -> set[str]:
    """从 ASN.1 文本中抽取所有类似标识符的 token。"""
    return set(re.findall(r"[A-Za-z][A-Za-z0-9-]*", text))


def load_blocks_by_content(blocks_dir: Path, root: Path) -> list[Block]:
    """加载每个 block 文件的“整段规范化文本”（用于 content 模式）。"""
    blocks: list[Block] = []
    for path in sorted(blocks_dir.glob("*.txt")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        canon = canonicalize(raw)
        if not canon:
            continue
        blocks.append(Block(path=path.relative_to(root).as_posix(), canonical_text=canon))
    return blocks


@dataclass(frozen=True)
class BlockFile:
    path: str
    def_blocks: tuple[str, ...]


def load_blocks_by_definitions(blocks_dir: Path, root: Path) -> list[BlockFile]:
    """加载每个 .txt，并提取其内部的每个 `::=` 定义块（defs 模式核心）。

    判定规则（defs 模式）：
    - 对每个 asn1_blocks/*.txt：提取若干定义块 def_blocks
    - 对某个 extracted/*.asn：如果它包含 def_blocks 中任意一个块（空白规范化后），
      就认为该 .txt 文件被该 .asn “用到”。

    这样可以解决：
    - .txt 里的多段定义在 .asn 中被拆散/夹杂其它定义时，整段不连续导致漏匹配的问题。
    """

    out: list[BlockFile] = []
    for path in sorted(blocks_dir.glob("*.txt")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        def_blocks = [canonicalize(b) for b in extract_definition_blocks(raw)]
        def_blocks = [b for b in def_blocks if b]
        if not def_blocks:
            continue
        out.append(
            BlockFile(
                path=path.relative_to(root).as_posix(),
                def_blocks=tuple(def_blocks),
            )
        )
    return out


def generate_mapping_by_content(root: Path, extracted_dir: Path, blocks_dir: Path) -> dict[str, list[str]]:
    """content 模式：要求整段 .txt 内容（规范化后）在 .asn 中连续出现。"""
    blocks = load_blocks_by_content(blocks_dir, root)
    mapping: dict[str, list[str]] = {}

    for asn_path in sorted(extracted_dir.glob("*.asn")):
        asn_text = canonicalize(asn_path.read_text(encoding="utf-8", errors="ignore"))
        matches = [b.path for b in blocks if b.canonical_text in asn_text]
        mapping[asn_path.name] = matches
    return mapping


def generate_mapping_by_definitions(root: Path, extracted_dir: Path, blocks_dir: Path) -> dict[str, list[str]]:
    """defs 模式（默认/推荐）：按每条 `::=` 定义块做包含判断。"""
    block_files = load_blocks_by_definitions(blocks_dir, root)
    mapping: dict[str, list[str]] = {}

    for asn_path in sorted(extracted_dir.glob("*.asn")):
        asn_text = canonicalize(asn_path.read_text(encoding="utf-8", errors="ignore"))
        matches: list[str] = []
        for bf in block_files:
            if any(def_block in asn_text for def_block in bf.def_blocks):
                matches.append(bf.path)
        mapping[asn_path.name] = matches
    return mapping


def generate_mapping_by_name(root: Path, extracted_dir: Path, blocks_dir: Path) -> dict[str, list[str]]:
    """name 模式：按 token 命中文件名（去后缀）来匹配，适合快速粗筛。"""
    block_index = build_block_index(blocks_dir, root)
    mapping: dict[str, list[str]] = {}

    for asn_path in sorted(extracted_dir.glob("*.asn")):
        text = asn_path.read_text(encoding="utf-8", errors="ignore")
        tokens = collect_tokens(text)
        matches = [block_index[t] for t in sorted(tokens) if t in block_index]
        mapping[asn_path.name] = matches
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ASN.1 block mapping for extracted files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root containing 'extracted' and 'asn1_blocks' directories.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file path (default: <root>/mapping/mapping.json)",
    )
    parser.add_argument(
        "--mode",
        choices=("defs", "content", "name"),
        default="defs",
        help=(
            "匹配模式：defs=按每条'::='定义块匹配(推荐)；"
            "content=整段txt连续包含；"
            "name=按token与文件名匹配(粗筛)"
        ),
    )
    args = parser.parse_args()

    root = args.root
    extracted_dir = root / "extracted"
    blocks_dir = root / "asn1_blocks"
    output = args.output or (root / "mapping" / "mapping.json")

    if args.mode == "defs":
        mapping = generate_mapping_by_definitions(root, extracted_dir, blocks_dir)
    elif args.mode == "content":
        mapping = generate_mapping_by_content(root, extracted_dir, blocks_dir)
    else:
        mapping = generate_mapping_by_name(root, extracted_dir, blocks_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote mapping to {output}")


if __name__ == "__main__":
    main()
