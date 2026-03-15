"""
逐行输出 payload 文件中每一行识别出的字段类型。

用法（在项目根目录执行）：
  python -m bishe.mutated.tools.print_each_line_type
  python -m bishe.mutated.tools.print_each_line_type --limit 20
  python -m bishe.mutated.tools.print_each_line_type --file rrc_legitimate_payloads_1773492110.txt
"""
import os
import sys
import argparse

# 项目根
_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from bishe.mutated.tools.field_type_inspector import inspect_field_type


DEFAULT_INPUT_DIR = os.path.join(
    _project_root, "bishe", "generate_new", "output_4g"
)


def main():
    parser = argparse.ArgumentParser(description="逐行输出每行的字段类型")
    parser.add_argument(
        "--input-dir", "-i",
        default=DEFAULT_INPUT_DIR,
        help="payload 文件所在目录",
    )
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="只处理指定文件名，如 rrc_legitimate_payloads_1773492110.txt",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="每个文件最多处理行数",
    )
    parser.add_argument(
        "--sep",
        default="\t",
        help="输出列分隔符，默认 TAB",
    )
    args = parser.parse_args()

    input_dir = args.input_dir
    if not os.path.isdir(input_dir):
        print(f"错误: 目录不存在 {input_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted([
        f for f in os.listdir(input_dir)
        if f.startswith("rrc_legitimate_payloads") and f.endswith(".txt")
    ])
    if args.file:
        if args.file in files:
            files = [args.file]
        else:
            print(f"错误: 未找到文件 {args.file}", file=sys.stderr)
            sys.exit(1)
    if not files:
        print(f"错误: 未找到 rrc_legitimate_payloads*.txt", file=sys.stderr)
        sys.exit(1)

    sep = args.sep
    print(sep.join(["file", "line_no", "idx", "message_type", "field_type", "supported", "path_abbr"]))

    for basename in files:
        in_path = os.path.join(input_dir, basename)
        count = 0
        with open(in_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                if args.limit is not None and count >= args.limit:
                    break
                parts = line.split(",")
                if len(parts) < 4:
                    print(sep.join([basename, str(line_no), "", "", "INVALID_LINE", "false", line[:60]]))
                    count += 1
                    continue
                idx = parts[0].strip()
                uper_hex = parts[1].strip()
                message_type = parts[2].strip()
                target_path = [p.strip() for p in parts[3:]]
                info = inspect_field_type(uper_hex=uper_hex, target_path=target_path)
                field_type = info.get("field_type", "")
                supported = info.get("supported", "false")
                path_abbr = ".".join(target_path[-3:]) if len(target_path) > 3 else ".".join(target_path)
                print(sep.join([basename, str(line_no), idx, message_type, field_type, supported, path_abbr]))
                count += 1


if __name__ == "__main__":
    main()
