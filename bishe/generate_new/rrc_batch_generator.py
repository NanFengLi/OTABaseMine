"""
RRC 合法样例批量生成器

驱动 RRCGenerator 批量生成覆盖所有目标字段路径的合法 RRC 数据包，
追踪路径覆盖率，输出到文件。

路径去重使用 SQLite 持久化前缀树（PathTrieDB），支持断点续传：
进程中断后重新运行相同命令，会自动检测已有覆盖数据并从断点继续。

这是整个生成流程的核心调度器，等价于原始代码中 RRCFuzzer.fill_queue()
+ RRCController 的"仅生成"功能，去除了变异策略。
"""
import os
import json
import time
import logging
import random
import re
from copy import deepcopy

from bishe.generate_new.rrc_generator import RRCGenerator
from bishe.generate_new.rrc_fields import Fields
from bishe.generate_new.rrc_stats import get_target_field_count, get_total_ie_count
from bishe.generate_new.rrc_utils import simplify_message
from bishe.generate_new.rrc_protocol import RRCContext
from bishe.generate_new.config import GeneratorConfig
from bishe.generate_new.path_trie import PathTrieDB

_PAYLOAD_RE = re.compile(r"^rrc_legitimate_payloads_(\d+)\.txt$")


class RRCBatchGenerator:
    """
    RRC 合法样例批量生成器

    系统性地生成合法 RRC DL-DCCH-Message 数据包，确保覆盖
    所有目标字段路径。输出格式兼容 OTABase 执行框架。

    路径去重通过 SQLite 前缀树持久化，支持断点续传。

    Attributes:
        targets:    目标字段类型列表
        seed:       随机种子
        cycles:     生成循环次数
        optional:   是否包含可选字段
        simplify:   是否精简消息（去除无关可选字段）
        db_path:    SQLite 前缀树数据库路径
    """

    def __init__(self, targets=None, seed=1, cycles=1,
                 max_recur_depth=0, optional=True, simplify=True,
                 rrc_ctx: RRCContext = None, db_path: str = None):
        """
        初始化批量生成器

        Args:
            targets:          目标字段类型列表，默认 [OCTET_STRING]
            seed:             随机种子
            cycles:           生成循环次数（每个循环覆盖所有目标路径一次）
            max_recur_depth:  最大递归展开深度
            optional:         是否生成可选字段
            rrc_ctx:          RRC 协议上下文
            db_path:          SQLite 前缀树数据库路径（None 则不持久化）
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
        self.db_path = db_path

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
        logging.info(f"  目标路径总数: {self.total_targets} (理论上限，实际可达路径数以生成结果为准)")
        logging.info(f"  IE 总数: {self.total_ie_count}")
        logging.info(f"  循环次数: {cycles}")
        logging.info(f"  随机种子: {seed}")
        if db_path:
            logging.info(f"  前缀树数据库: {db_path}")

    # ------------------------------------------------------------------
    # 输出文件扫描（断点续传用）
    # ------------------------------------------------------------------

    @staticmethod
    def _count_data_lines(filepath: str) -> int:
        """统计 payload 文件中的数据行数（排除第一行的计数占位行）。"""
        count = 0
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i == 0:
                        continue  # 跳过第一行（计数行）
                    if line.strip():
                        count += 1
        except OSError:
            pass
        return count

    @staticmethod
    def _scan_payload_files(out_dir: str):
        """
        扫描输出目录中已有的 payload 文件。

        Returns:
            list of (filepath, timestamp, data_line_count) 按 timestamp 升序
        """
        results = []
        if not out_dir or not os.path.isdir(out_dir):
            return results
        for fname in os.listdir(out_dir):
            m = _PAYLOAD_RE.match(fname)
            if m:
                ts = int(m.group(1))
                fpath = os.path.join(out_dir, fname)
                count = RRCBatchGenerator._count_data_lines(fpath)
                results.append((fpath, ts, count))
        results.sort(key=lambda x: x[1])
        return results

    # ------------------------------------------------------------------
    # 核心生成
    # ------------------------------------------------------------------

    def generate_all(self, output_file=None, verbose=True, max_lines_per_file=2000):
        """
        批量生成合法 RRC 数据包，覆盖所有目标字段路径。

        使用 SQLite 前缀树持久化路径覆盖状态，支持断点续传：
        如果 db_path 指向的数据库已有覆盖数据且参数一致，
        会自动跳过已覆盖路径，从上次中断处继续生成。

        Args:
            output_file:  输出目录路径或文件路径（取其所在目录）；
                          None 则只返回结果不写文件
            verbose:      是否打印进度信息
            max_lines_per_file:  单个文件最多写入的载荷条数 (默认 2000)

        Returns:
            dict: 生成结果统计
        """
        start_time = time.time()
        all_payloads = []
        total_packets_generated = 0
        payload_index = 0
        file_payload_count = 0
        file_number = 1
        output_files = []

        # ---------- 输出目录 ----------
        out_dir = None
        base_timestamp = int(time.time())
        out_fh = None

        if output_file:
            if os.path.isdir(output_file):
                out_dir = output_file
            else:
                out_dir = os.path.dirname(output_file) or '.'
            os.makedirs(out_dir, exist_ok=True)

        # ---------- 打开前缀树 ----------
        trie = None
        if self.db_path:
            trie = PathTrieDB(self.db_path)

        resuming = False
        targets_json = json.dumps(sorted(t.name for t in self.targets))

        # ---------- 断点续传检测 ----------
        if trie and trie.count() > 0:
            state = trie.load_state()
            saved_targets = state.get("targets")
            if saved_targets == targets_json:
                covered = trie.count()
                if covered >= self.total_targets:
                    logging.info(f"前缀树显示所有 {self.total_targets} 条路径已覆盖，无需继续。")
                    if trie:
                        trie.close()
                    return {
                        'payloads': [],
                        'total_count': covered,
                        'packets_generated': 0,
                        'coverage': 1.0,
                        'unique_paths': covered,
                        'elapsed_time': 0.0,
                        'seed': self.seed,
                        'cycles': self.cycles,
                        'targets': [t.name for t in self.targets],
                        'output_files': [],
                        'max_lines_per_file': max_lines_per_file,
                        'resumed': True,
                    }

                resuming = True
                base_timestamp = state.get("base_timestamp", base_timestamp)
                saved_payload_index = state.get("payload_index", 0)

                # 恢复 generator 的 found_paths
                existing_paths = trie.all_paths()
                self.generator.set_found_paths(existing_paths)

                # 扫描属于本次运行的已有文件（按 base_timestamp 过滤）
                all_files = self._scan_payload_files(out_dir)
                existing_files = [
                    ef for ef in all_files if ef[1] >= base_timestamp
                ]
                payload_index = saved_payload_index
                if existing_files:
                    output_files = [ef[0] for ef in existing_files]
                    last_path, last_ts, last_count = existing_files[-1]
                    file_number = last_ts - base_timestamp + 1
                    file_payload_count = last_count

                    if last_count >= max_lines_per_file:
                        file_number += 1
                        file_payload_count = 0
                    else:
                        # 追加到最后一个未满文件
                        output_files.pop()  # 稍后由 _open_resume_file 重新添加

                logging.info(
                    f"  [断点续传] 已覆盖 {covered}/{self.total_targets} 条路径, "
                    f"已写入 {payload_index} 条载荷, "
                    f"继续从文件 #{file_number} 开始")
            else:
                logging.warning(
                    f"  前缀树 targets 不匹配 (DB={saved_targets}, "
                    f"当前={targets_json})，将清空重建。")
                trie.close()
                os.remove(self.db_path)
                trie = PathTrieDB(self.db_path)

        # ---------- 保存初始状态 ----------
        if trie and not resuming:
            trie.save_states({
                "base_timestamp": base_timestamp,
                "payload_index": 0,
                "targets": targets_json,
                "total_targets": self.total_targets,
            })

        # ---------- 文件打开辅助函数 ----------
        def _open_new_file():
            """打开一个全新的 payload 输出文件。"""
            ts = base_timestamp + (file_number - 1)
            fname = f"rrc_legitimate_payloads_{ts}.txt"
            fpath = os.path.join(out_dir, fname)
            fh = open(fpath, 'w')
            fh.write('000000\n')
            output_files.append(fpath)
            if verbose:
                logging.info(f"  打开新文件: {fpath}")
            return fh, fpath

        def _open_resume_file():
            """以追加模式打开上次未写满的文件。"""
            ts = base_timestamp + (file_number - 1)
            fname = f"rrc_legitimate_payloads_{ts}.txt"
            fpath = os.path.join(out_dir, fname)
            fh = open(fpath, 'r+')
            fh.seek(0, 2)  # seek 到末尾
            output_files.append(fpath)
            if verbose:
                logging.info(f"  [续传] 追加写入: {fpath} (已有 {file_payload_count} 行)")
            return fh, fpath

        def _close_file(fh, count):
            """回填当前文件的条数并关闭。"""
            if fh and not fh.closed:
                fh.seek(0)
                fh.write(str(count).zfill(6))
                fh.close()

        # ---------- 打开输出文件 ----------
        cur_file_path = None
        if out_dir:
            if resuming and file_payload_count > 0 and file_payload_count < max_lines_per_file:
                out_fh, cur_file_path = _open_resume_file()
            else:
                out_fh, cur_file_path = _open_new_file()

        try:
            for cycle in range(1, self.cycles + 1):
                if verbose:
                    logging.info(f"--- 开始第 {cycle}/{self.cycles} 轮生成 ---")

                if not resuming:
                    self.generator.reset_found()
                    if trie:
                        # 全新 cycle：清空前缀树（多 cycle 场景）
                        pass  # 第一轮 trie 本来就是空的

                already_covered = trie.count() if trie else 0
                stall_counter = 0
                STALL_THRESHOLD = 2000

                while (trie.count() if trie else already_covered) < self.total_targets:
                    uper_bytes, result, mutation_paths, optional_paths = \
                        self.generator.generate_packet()
                    total_packets_generated += 1

                    if len(mutation_paths) == 0:
                        stall_counter += 1
                        if stall_counter >= STALL_THRESHOLD:
                            covered_now = trie.count() if trie else len(self.generator.found_paths)
                            logging.warning(
                                f"连续 {STALL_THRESHOLD} 个包未发现新路径，"
                                f"判定所有可达路径已覆盖 "
                                f"({covered_now}/{self.total_targets})")
                            break
                        continue

                    new_paths = []
                    for path in mutation_paths:
                        unique_path = tuple(
                            [x for x in path if not isinstance(x, int)])
                        is_new = trie.insert(unique_path) if trie else (unique_path not in self.generator.found_paths)
                        if is_new:
                            self.generator.add_to_found(unique_path)
                            new_paths.append((path, unique_path))

                    if not new_paths:
                        stall_counter += 1
                        if stall_counter >= STALL_THRESHOLD:
                            covered_now = trie.count() if trie else len(self.generator.found_paths)
                            logging.warning(
                                f"连续 {STALL_THRESHOLD} 个包未发现新路径，"
                                f"判定所有可达路径已覆盖 "
                                f"({covered_now}/{self.total_targets})")
                            break
                        continue

                    stall_counter = 0

                    if self.simplify:
                        result_copy = deepcopy(result)
                    else:
                        result_copy = None

                    full_hex = uper_bytes.hex() if not self.simplify else None

                    for path, unique_path in new_paths:
                        if self.simplify:
                            payload_hex = self._simplify_and_encode(
                                deepcopy(result_copy), path, optional_paths)
                        else:
                            payload_hex = full_hex

                        msg_type = unique_path[2] if len(unique_path) > 2 else "unknown"
                        field_path_str = ",".join(str(x) for x in path)

                        payload_index += 1
                        file_payload_count += 1
                        entry = (payload_hex, msg_type, field_path_str)
                        all_payloads.append(entry)

                        if out_fh:
                            out_fh.write(
                                f"{file_payload_count},{payload_hex},"
                                f"{msg_type},{field_path_str}\n")
                            out_fh.flush()

                            if file_payload_count >= max_lines_per_file:
                                _close_file(out_fh, file_payload_count)
                                if verbose:
                                    logging.info(
                                        f"  文件 {cur_file_path} 已满 "
                                        f"({file_payload_count} 条)，切换到下一个文件")
                                file_number += 1
                                file_payload_count = 0
                                out_fh, cur_file_path = _open_new_file()

                    # 持久化进度
                    if trie:
                        trie.save_state("payload_index", payload_index)

                    covered_now = trie.count() if trie else len(self.generator.found_paths)
                    if verbose and total_packets_generated % 50 == 0:
                        coverage = covered_now / self.total_targets
                        logging.info(
                            f"  进度: 已生成 {total_packets_generated} 个包, "
                            f"覆盖 {covered_now}/{self.total_targets} "
                            f"({coverage:.1%})")

                # cycle 结束后重置续传标记，后续 cycle 从空开始
                resuming = False

                covered_now = trie.count() if trie else len(self.generator.found_paths)
                coverage_pct = covered_now / self.total_targets if self.total_targets else 1.0
                if verbose:
                    logging.info(
                        f"  第 {cycle} 轮完成: "
                        f"生成 {payload_index} 个有效载荷, "
                        f"覆盖 {covered_now}/{self.total_targets} "
                        f"({coverage_pct:.1%})")

        finally:
            if out_fh:
                _close_file(out_fh, file_payload_count)
                if verbose:
                    logging.info(f"  已写入 {file_payload_count} 条载荷到 {cur_file_path}")

            if out_dir and output_files:
                index_path = os.path.join(out_dir, "testFileIndex")
                first_file_basename = os.path.basename(output_files[0])
                with open(index_path, 'w') as idx_f:
                    idx_f.write(f"{first_file_basename}\n")
                if verbose:
                    logging.info(f"  已生成 testFileIndex -> {first_file_basename}")
                    logging.info(f"  共生成 {len(output_files)} 个 payload 文件: "
                                 f"{', '.join(os.path.basename(f) for f in output_files)}")

            if trie:
                trie.save_state("payload_index", payload_index)
                final_covered = trie.count()
                trie.close()
            else:
                final_covered = payload_index

        elapsed = time.time() - start_time
        final_coverage = final_covered / self.total_targets if self.total_targets else 1.0
        result = {
            'payloads': all_payloads,
            'total_count': payload_index,
            'packets_generated': total_packets_generated,
            'coverage': final_coverage,
            'unique_paths': final_covered,
            'total_targets': self.total_targets,
            'elapsed_time': elapsed,
            'seed': self.seed,
            'cycles': self.cycles,
            'targets': [t.name for t in self.targets],
            'output_files': [os.path.basename(f) for f in output_files],
            'max_lines_per_file': max_lines_per_file,
            'resumed': resuming,
        }

        if verbose:
            logging.info(f"\n=== 生成完成 ===")
            logging.info(f"  合法载荷总数: {result['total_count']}")
            logging.info(f"  总共生成包数: {total_packets_generated}")
            logging.info(f"  可达路径覆盖: {final_covered}/{self.total_targets} ({final_coverage:.1%})")
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
