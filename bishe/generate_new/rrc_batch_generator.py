"""
RRC 合法样例批量生成器

驱动 RRCGenerator 批量生成覆盖所有目标字段路径的合法 RRC 数据包，
追踪路径覆盖率，输出到文件。

这是整个生成流程的核心调度器，等价于原始代码中 RRCFuzzer.fill_queue()
+ RRCController 的"仅生成"功能，去除了变异策略。
"""
import os
import json
import time
import logging
import random
from copy import deepcopy

from bishe.generate_new.rrc_generator import RRCGenerator
from bishe.generate_new.rrc_fields import Fields
from bishe.generate_new.rrc_stats import get_target_field_count, get_total_ie_count
from bishe.generate_new.rrc_utils import simplify_message
from bishe.generate_new.rrc_protocol import RRCContext
from bishe.generate_new.config import GeneratorConfig


class RRCBatchGenerator:
    """
    RRC 合法样例批量生成器

    系统性地生成合法 RRC DL-DCCH-Message 数据包，确保覆盖
    所有目标字段路径。输出格式兼容 OTABase 执行框架。

    Attributes:
        targets:    目标字段类型列表
        seed:       随机种子
        cycles:     生成循环次数
        optional:   是否包含可选字段
        simplify:   是否精简消息（去除无关可选字段）
    """

    def __init__(self, targets=None, seed=1, cycles=1,
                 max_recur_depth=0, optional=True, simplify=True,
                 rrc_ctx: RRCContext = None):
        """
        初始化批量生成器

        Args:
            targets:          目标字段类型列表，默认 [OCTET_STRING]
            seed:             随机种子
            cycles:           生成循环次数（每个循环覆盖所有目标路径一次）
            max_recur_depth:  最大递归展开深度
            optional:         是否生成可选字段
            rrc_ctx:          RRC 协议上下文
        """
        if targets is None:
            targets = [Fields.OCTET_STRING]

        self.targets = targets
        self.seed = seed
        self.cycles = cycles
        self.optional = optional
        self.max_recur_depth = max_recur_depth
        self.simplify = simplify
        self.rrc_ctx = rrc_ctx

        random.seed(seed)

        # 初始化生成器
        self.generator = RRCGenerator(
            targets=targets,
            max_recur_depth=max_recur_depth,
            seed=seed,
            optional=optional,
            rrc_ctx=rrc_ctx
        )

        # 计算目标字段总数（用于覆盖率计算）
        w_recur = not (max_recur_depth == 0)
        self.total_targets = get_target_field_count(
            targets=targets, w_recur=w_recur, message=rrc_ctx.dl_dcch_message)
        self.total_ie_count = get_total_ie_count(
            message=rrc_ctx.dl_dcch_message)

        logging.info(f"RRC 批量生成器初始化完成:")
        logging.info(f"  目标字段类型: {[t.name for t in targets]}")
        logging.info(f"  目标路径总数: {self.total_targets}")
        logging.info(f"  IE 总数: {self.total_ie_count}")
        logging.info(f"  循环次数: {cycles}")
        logging.info(f"  随机种子: {seed}")

    def generate_all(self, output_file=None, verbose=True, max_lines_per_file=2000):
        """
        批量生成合法 RRC 数据包，覆盖所有目标字段路径。
        支持流式写入：每生成一条载荷立即写入文件。
        当单个文件达到 max_lines_per_file 条后自动切换到下一个文件。

                文件命名规则：
                    输出目录下生成 rrc_legitimate_payloads_<timestamp>.txt 系列文件，
                    当超过单文件条数上限时，timestamp 递增后继续写入下一个文件。
                    同时生成 testFileIndex 指向第一个文件。
                    文件名格式兼容 OTABase 的 increment_otabase_filename() 自动递增逻辑。

        Args:
            output_file:  输出目录路径或文件路径（取其所在目录）；
                          None 则只返回结果不写文件
            verbose:      是否打印进度信息
            max_lines_per_file:  单个文件最多写入的载荷条数 (默认 2000)

        Returns:
            dict: 生成结果，包含:
                - payloads:       [(hex_payload, msg_type, field_path), ...]
                - total_count:    生成的数据包总数
                - coverage:       最终覆盖率
                - unique_paths:   唯一路径数
                - elapsed_time:   耗时（秒）
                - output_files:   生成的所有 payload 文件路径列表
        """
        start_time = time.time()
        all_payloads = []
        total_packets_generated = 0
        payload_index = 0          # 全局载荷序号
        file_payload_count = 0     # 当前文件中的载荷数
        file_number = 1            # 当前文件编号
        output_files = []          # 所有生成的文件路径

        # ---------- 输出目录与文件名 ----------
        out_dir = None
        base_timestamp = int(time.time())
        out_fh = None

        if output_file:
            # 从 output_file 提取目录
            if os.path.isdir(output_file):
                out_dir = output_file
            else:
                out_dir = os.path.dirname(output_file) or '.'
            os.makedirs(out_dir, exist_ok=True)

        def _open_new_file():
            """打开一个新的 payload 输出文件，返回 (file_handle, filepath)。"""
            ts = base_timestamp + (file_number - 1)
            fname = f"rrc_legitimate_payloads_{ts}.txt"
            fpath = os.path.join(out_dir, fname)
            fh = open(fpath, 'w')
            fh.write('000000\n')  # 占位行，结束时回填实际条数
            output_files.append(fpath)
            if verbose:
                logging.info(f"  打开新文件: {fpath}")
            return fh, fpath

        def _close_file(fh, count):
            """回填当前文件的条数并关闭。"""
            if fh and not fh.closed:
                fh.seek(0)
                fh.write(str(count).zfill(6))
                fh.close()

        # 打开第一个文件
        cur_file_path = None
        if out_dir:
            out_fh, cur_file_path = _open_new_file()

        try:
            for cycle in range(1, self.cycles + 1):
                if verbose:
                    logging.info(f"--- 开始第 {cycle}/{self.cycles} 轮生成 ---")

                coverage_map = set()
                self.generator.reset_found()

                while len(coverage_map) < self.total_targets:
                    # 生成一个完整数据包
                    uper_bytes, result, mutation_paths, optional_paths = \
                        self.generator.generate_packet()
                    total_packets_generated += 1

                    if len(mutation_paths) == 0:
                        continue

                    # 收集本包的新路径，一次性精简
                    new_paths = []
                    for path in mutation_paths:
                        unique_path = tuple(
                            [x for x in path if not isinstance(x, int)])
                        if unique_path not in coverage_map:
                            self.generator.add_to_found(unique_path)
                            coverage_map.add(unique_path)
                            new_paths.append((path, unique_path))

                    if not new_paths:
                        continue

                    # 如果需要精简，对整包做一次 deepcopy
                    if self.simplify:
                        result_copy = deepcopy(result)
                    else:
                        result_copy = None

                    # 直接使用完整包的 hex（不精简时）
                    full_hex = uper_bytes.hex() if not self.simplify else None

                    for path, unique_path in new_paths:
                        if self.simplify:
                            payload_hex = self._simplify_and_encode(
                                deepcopy(result_copy), path, optional_paths)
                        else:
                            payload_hex = full_hex

                        msg_type = unique_path[2] if len(unique_path) > 2 else "unknown"
                        # 与 artifact 一致：写入完整 path（含 SEQUENCE OF 下标），供变异时 get_val_at 使用
                        field_path_str = ",".join(str(x) for x in path)

                        payload_index += 1
                        file_payload_count += 1
                        entry = (payload_hex, msg_type, field_path_str)
                        all_payloads.append(entry)

                        # 流式写入
                        if out_fh:
                            out_fh.write(
                                f"{file_payload_count},{payload_hex},"
                                f"{msg_type},{field_path_str}\n")
                            out_fh.flush()

                            # 检查是否需要切换到下一个文件
                            if file_payload_count >= max_lines_per_file:
                                _close_file(out_fh, file_payload_count)
                                if verbose:
                                    logging.info(
                                        f"  文件 {cur_file_path} 已满 "
                                        f"({file_payload_count} 条)，切换到下一个文件")
                                file_number += 1
                                file_payload_count = 0
                                out_fh, cur_file_path = _open_new_file()

                    # 进度日志
                    coverage = len(coverage_map) / self.total_targets
                    if verbose and total_packets_generated % 50 == 0:
                        logging.info(
                            f"  进度: 已生成 {total_packets_generated} 个包, "
                            f"覆盖 {len(coverage_map)}/{self.total_targets} "
                            f"({coverage:.1%})")

                if verbose:
                    logging.info(
                        f"  第 {cycle} 轮完成: "
                        f"生成 {payload_index} 个有效载荷, "
                        f"覆盖率: 100%")

        finally:
            # 回填最后一个文件的条数并关闭
            if out_fh:
                _close_file(out_fh, file_payload_count)
                if verbose:
                    logging.info(f"  已写入 {file_payload_count} 条载荷到 {cur_file_path}")

            # 生成 testFileIndex，指向第一个文件（使用相对文件名）
            if out_dir and output_files:
                index_path = os.path.join(out_dir, "testFileIndex")
                first_file_basename = os.path.basename(output_files[0])
                with open(index_path, 'w') as idx_f:
                    idx_f.write(f"{first_file_basename}\n")
                if verbose:
                    logging.info(f"  已生成 testFileIndex -> {first_file_basename}")
                    logging.info(f"  共生成 {len(output_files)} 个 payload 文件: "
                                 f"{', '.join(os.path.basename(f) for f in output_files)}")

        elapsed = time.time() - start_time

        result = {
            'payloads': all_payloads,
            'total_count': len(all_payloads),
            'packets_generated': total_packets_generated,
            'coverage': 1.0,
            'unique_paths': self.total_targets,
            'elapsed_time': elapsed,
            'seed': self.seed,
            'cycles': self.cycles,
            'targets': [t.name for t in self.targets],
            'output_files': [os.path.basename(f) for f in output_files],
            'max_lines_per_file': max_lines_per_file,
        }

        if verbose:
            logging.info(f"\n=== 生成完成 ===")
            logging.info(f"  合法载荷总数: {result['total_count']}")
            logging.info(f"  总共生成包数: {total_packets_generated}")
            logging.info(f"  输出文件数: {len(output_files)}")
            logging.info(f"  耗时: {elapsed:.2f} 秒")

        return result

    def _simplify_and_encode(self, packet_fields: dict, target_path: list,
                              optional_paths: list) -> str:
        """
        将完整消息精简为仅包含到达目标字段所需字段的最小消息，
        然后重新 UPER 编码。

        Args:
            packet_fields:  完整消息字典（会被修改，传入前应 deepcopy）
            target_path:    目标字段路径
            optional_paths: 所有可选字段路径列表

        Returns:
            str: 精简后消息的 UPER 十六进制字符串
        """
        try:
            simplified_fields = simplify_message(
                packet_fields, target_path, optional_paths,
                global_mod=self.rrc_ctx.global_mod)

            # 重新编码
            packet_obj = self.rrc_ctx.dl_dcch_message
            packet_obj.set_val(simplified_fields)
            return packet_obj.to_uper().hex()
        except Exception as e:
            logging.warning(f"精简失败，回退使用完整消息: {e}")
            # 回退：用原始完整消息编码
            packet_obj = self.rrc_ctx.dl_dcch_message
            packet_obj.set_val(packet_fields)
            return packet_obj.to_uper().hex()

    def generate_single(self):
        """
        生成单个合法 RRC 数据包

        Returns:
            tuple: (hex_payload, result_dict, mutation_paths, optional_paths)
        """
        uper_bytes, result, mutation_paths, optional_paths = \
            self.generator.generate_packet()
        return uper_bytes.hex(), result, mutation_paths, optional_paths

    def generate_single_simplified(self, target_path_index=0):
        """
        生成单个精简的合法 RRC 数据包

        Args:
            target_path_index: 选择第几条目标路径来精简（默认第0条）

        Returns:
            tuple: (simplified_hex, target_path, msg_type)
        """
        uper_bytes, result, mutation_paths, optional_paths = \
            self.generator.generate_packet()

        if not mutation_paths:
            return uper_bytes.hex(), [], "unknown"

        idx = min(target_path_index, len(mutation_paths) - 1)
        target_path = mutation_paths[idx]
        unique_path = tuple([x for x in target_path if not isinstance(x, int)])
        msg_type = unique_path[2] if len(unique_path) > 2 else "unknown"

        simplified_hex = self._simplify_and_encode(
            deepcopy(result), target_path, optional_paths)

        return simplified_hex, target_path, msg_type

    def _write_payload_file(self, filepath, payloads):
        """
        将生成的载荷写入文件，格式兼容 OTABase 执行框架

        文件格式:
            <total_payload_count>
            <payload_id>,<hex_payload>,<target_message_type>,<target_field_path>
            ...

        Args:
            filepath: 输出文件路径
            payloads: [(hex_payload, msg_type, field_path), ...] 列表
        """
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

        total = len(payloads)
        total_width = 6
        formatted_total = str(total).zfill(total_width)

        with open(filepath, 'w') as f:
            f.write(f"{formatted_total}\n")
            for i, (hex_payload, msg_type, field_path) in enumerate(payloads, 1):
                f.write(f"{i},{hex_payload},{msg_type},{field_path}\n")

        logging.info(f"已写入 {total} 条载荷到 {filepath}")

    def write_report(self, report_file, result, append=False):
        """
        将生成报告写入 JSON 文件

        Args:
            report_file: 报告文件路径
            result: generate_all() 的返回结果
            append: 是否追加写入（True 时会将报告追加到 JSON 列表）
        """
        os.makedirs(os.path.dirname(report_file) if os.path.dirname(report_file) else '.', exist_ok=True)

        report = {k: v for k, v in result.items() if k != 'payloads'}
        report['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')

        if not append:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logging.info(f"已写入生成报告到 {report_file}")
            return

        existing_reports = []
        if os.path.exists(report_file):
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    old_content = json.load(f)
                if isinstance(old_content, list):
                    existing_reports = old_content
                elif isinstance(old_content, dict):
                    # 兼容旧版本单对象格式，自动升级为列表
                    existing_reports = [old_content]
                else:
                    logging.warning(f"报告文件格式非对象/数组，将覆盖重建: {report_file}")
            except (json.JSONDecodeError, OSError) as e:
                logging.warning(f"读取历史报告失败，将覆盖重建: {report_file}, error={e}")

        existing_reports.append(report)

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(existing_reports, f, indent=2, ensure_ascii=False)

        logging.info(f"已追加生成报告到 {report_file} (当前 {len(existing_reports)} 条)")
