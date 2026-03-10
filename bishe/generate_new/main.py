"""
RRC 合法测试样例生成器 - 主入口

用法:
    # 使用默认配置生成（目标: OCTET_STRING，协议: 4G LTE）
    python -m bishe.generate_new.main

    # 指定目标字段类型
    python -m bishe.generate_new.main -f OCTET_STRING BIT_STRING INTEGER SEQOF

    # 生成 5G NR 的 RRC 消息
    python -m bishe.generate_new.main --rat 5g

    # 指定输出文件、种子和循环次数(循环次数是指有些字段会循环嵌套使用，嵌套的深度即为循环次数)
    python -m bishe.generate_new.main -f OCTET_STRING -s 42 -c 2 -o output_4g/rrc_payloads.txt

    # 生成单个数据包（测试模式）
    python -m bishe.generate_new.main -t single

    # 显示统计信息
    python -m bishe.generate_new.main -t stats
"""
import os
import sys
import argparse
import logging
import time

from bishe.generate_new.rrc_fields import Fields
from bishe.generate_new.rrc_generator import RRCGenerator
from bishe.generate_new.rrc_batch_generator import RRCBatchGenerator
from bishe.generate_new.rrc_stats import get_target_field_count, get_total_ie_count
from bishe.generate_new.rrc_protocol import RRCContext, RATType
from bishe.generate_new.config import GeneratorConfig


def setup_logging(level=logging.INFO):
    """配置日志"""
    logging.basicConfig(
        level=level,
        format='%(levelname)s - %(message)s',
        stream=sys.stdout
    )


def parse_target_fields(field_names: list) -> list:
    """将字符串字段名称列表转换为 Fields 枚举值列表"""
    return [Fields.from_name(name) for name in field_names]


def cmd_generate(args):
    """执行批量生成"""
    target_fields = parse_target_fields(args.fields)
    rrc_ctx = RRCContext(RATType(args.rat))

    logging.info(f"协议类型: {args.rat.upper()}")
    logging.info(f"目标字段: {', '.join(f.name for f in target_fields)}")
    logging.info(f"随机种子: {args.seed}")
    logging.info(f"循环次数: {args.cycles}")

    batch_gen = RRCBatchGenerator(
        targets=target_fields,
        seed=args.seed,
        cycles=args.cycles,
        max_recur_depth=args.recur_depth,
        optional=not args.no_optional,
        simplify=not args.no_simplify,
        rrc_ctx=rrc_ctx,
    )

    result = batch_gen.generate_all(
        output_file=args.output,
        verbose=True
    )

    # 写入报告
    if args.report:
        batch_gen.write_report(args.report, result, append=args.append_report)


def cmd_single(args):
    """生成单个数据包"""
    target_fields = parse_target_fields(args.fields)
    rrc_ctx = RRCContext(RATType(args.rat))

    generator = RRCGenerator(
        targets=target_fields,
        seed=args.seed,
        max_recur_depth=args.recur_depth,
        optional=not args.no_optional,
        rrc_ctx=rrc_ctx,
    )

    logging.info("生成单个合法 RRC 数据包:")
    uper_bytes, result, mutation_paths, optional_paths = generator.generate_packet()

    print(f"\nUPER Hex: {uper_bytes.hex()}")
    print(f"字节长度: {len(uper_bytes)}")
    print(f"可变异路径数: {len(mutation_paths)}")
    print(f"可选字段路径数: {len(optional_paths)}")

    if args.verbose:
        print(f"\n消息结构:")
        _print_dict(result, indent=2)
        print(f"\n可变异路径:")
        for i, p in enumerate(mutation_paths, 1):
            print(f"  {i}. {' -> '.join(str(x) for x in p)}")


def cmd_stats(args):
    """显示统计信息"""
    rrc_ctx = RRCContext(RATType(args.rat))
    all_targets = [Fields.BIT_STRING, Fields.OCTET_STRING, Fields.INTEGER, Fields.SEQOF]

    rat_label = "LTE 4G" if args.rat == "4g" else "NR 5G"
    print("=" * 60)
    print(f"RRC DL-DCCH-Message 目标字段统计 ({rat_label})")
    print("=" * 60)

    total_ie = get_total_ie_count(message=rrc_ctx.dl_dcch_message)
    print(f"\nIE 总数: {total_ie}")

    for target in all_targets:
        count = get_target_field_count(
            targets=[target], w_recur=False, message=rrc_ctx.dl_dcch_message)
        print(f"  {target.name:15s}: {count} 个可变异路径")

    all_count = get_target_field_count(
        targets=all_targets, w_recur=False, message=rrc_ctx.dl_dcch_message)
    print(f"  {'ALL':15s}: {all_count} 个可变异路径")
    print()


def cmd_benchmark(args):
    """基准测试"""
    target_fields = parse_target_fields(args.fields)
    rrc_ctx = RRCContext(RATType(args.rat))

    generator = RRCGenerator(
        targets=target_fields,
        seed=args.seed,
        rrc_ctx=rrc_ctx,
    )

    n_tests = args.benchmark_count
    logging.info(f"基准测试: 生成 {n_tests} 个数据包")

    times = []
    for i in range(n_tests):
        start = time.time()
        generator.generate_packet()
        elapsed = time.time() - start
        times.append(elapsed)

    avg = sum(times) / len(times)
    logging.info(f"平均耗时: {avg:.4f} 秒/包")
    logging.info(f"最小耗时: {min(times):.4f} 秒")
    logging.info(f"最大耗时: {max(times):.4f} 秒")
    logging.info(f"总耗时: {sum(times):.2f} 秒")


def _print_dict(d, indent=0):
    """递归打印字典"""
    prefix = " " * indent
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list, tuple)):
                print(f"{prefix}{k}:")
                _print_dict(v, indent + 2)
            elif isinstance(v, bytes):
                print(f"{prefix}{k}: <{len(v)} bytes>")
            else:
                print(f"{prefix}{k}: {v}")
    elif isinstance(d, tuple) and len(d) == 2 and isinstance(d[0], str):
        print(f"{prefix}({d[0]}:")
        _print_dict(d[1], indent + 2)
        print(f"{prefix})")
    elif isinstance(d, list):
        for i, item in enumerate(d):
            print(f"{prefix}[{i}]:")
            _print_dict(item, indent + 2)
    else:
        print(f"{prefix}{d}")


def main():
    parser = argparse.ArgumentParser(
        description='RRC 合法测试样例生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成覆盖所有 OCTET_STRING 路径的合法载荷（4G）
  python -m bishe.generate_new.main -f OCTET_STRING

  # 生成 5G NR 的 RRC 消息
  python -m bishe.generate_new.main --rat 5g

  # 生成覆盖所有字段类型的合法载荷
  python -m bishe.generate_new.main -f BIT_STRING OCTET_STRING INTEGER SEQOF

  # 指定输出和种子
  python -m bishe.generate_new.main -f OCTET_STRING -s 42 -o output_4g/payloads.txt

  # 显示统计信息
  python -m bishe.generate_new.main -t stats

  # 显示 5G 统计信息
  python -m bishe.generate_new.main -t stats --rat 5g

  # 基准测试
  python -m bishe.generate_new.main -t benchmark -n 100
        """
    )

    parser.add_argument('-t', '--test', type=str,
                        choices=['single', 'stats', 'benchmark'],
                        help='测试模式: single(生成单包), stats(统计), benchmark(基准测试)')
    parser.add_argument('--rat', type=str,
                        choices=['4g', '5g'],
                        default='4g',
                        help='无线接入技术类型: 4g(LTE), 5g(NR) (默认: 4g)')
    parser.add_argument('-f', '--fields', type=str, nargs='+',
                        choices=['BIT_STRING', 'OCTET_STRING', 'INTEGER', 'SEQOF'],
                        default=['OCTET_STRING'],
                        help='目标字段类型 (默认: OCTET_STRING)')
    parser.add_argument('-c', '--cycles', type=int, default=1,
                        help='生成循环次数 (默认: 1)')
    parser.add_argument('-s', '--seed', type=int, default=1,
                        help='随机种子 (默认: 1)')
    parser.add_argument('-o', '--output', type=str,
                        default=None,
                        help='输出文件路径')
    parser.add_argument('-r', '--report', type=str, default=None,
                        help='生成报告 JSON 文件路径')
    parser.add_argument('--append-report', action='store_true',
                        help='追加写入报告（将每次运行追加到 JSON 列表）')
    parser.add_argument('--recur-depth', type=int, default=0,
                        help='最大递归展开深度 (默认: 0)')
    parser.add_argument('--no-optional', action='store_true',
                        help='不生成可选字段')
    parser.add_argument('--no-simplify', action='store_true',
                        help='跳过消息精简步骤（大幅加速，但消息体积更大）')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='启用调试日志')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='详细输出')
    parser.add_argument('-n', '--benchmark-count', type=int, default=100,
                        help='基准测试数据包数量 (默认: 100)')

    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)

    # 根据 RAT 类型设置默认输出路径
    output_subdir = "output_4g" if args.rat == "4g" else "output_5g"

    if args.output is None and args.test is None:
        out_dir = os.path.join(os.path.dirname(__file__), output_subdir)
        os.makedirs(out_dir, exist_ok=True)
        args.output = os.path.join(out_dir, GeneratorConfig.DEFAULT_OUTPUT_FILE)

    if args.report is None and args.test is None:
        out_dir = os.path.join(os.path.dirname(__file__), output_subdir)
        os.makedirs(out_dir, exist_ok=True)
        args.report = os.path.join(out_dir, GeneratorConfig.REPORT_FILE)

    # 执行
    if args.test == 'single':
        cmd_single(args)
    elif args.test == 'stats':
        cmd_stats(args)
    elif args.test == 'benchmark':
        cmd_benchmark(args)
    else:
        cmd_generate(args)


if __name__ == '__main__':
    main()
