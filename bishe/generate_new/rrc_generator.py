"""
RRC 合法样例生成器

递归遍历 ASN.1 语法树，根据 CHOICE 路径策略和目标字段类型，
生成符合 3GPP RRC 规范的合法 DL-DCCH-Message。

仅包含生成逻辑，不包含变异/fuzzing 策略。
从 OTABase artifact/test-case-generator/rrc/rrc_generator.py 抽取核心生成功能。
"""
from bishe.generate_new.releaseLTE_R17 import RRCLTE_R17
from bishe.generate_new.rrc_choices import get_choices
from bishe.generate_new.rrc_fields import Fields
from bishe.generate_new.rrc_stats import get_recursif_field_paths

import logging
import os
import random


class RRCGenerator:
    """
    RRC 合法消息生成器

    通过分析 ASN.1 语法树中的 CHOICE 路径，系统地生成能够覆盖
    所有目标字段类型的合法 DL-DCCH-Message。

    Attributes:
        targets:          目标字段类型列表 (Fields enum)
        max_recur_depth:  最大递归展开深度，默认 0
        seed:             随机数种子
        optional:         是否生成可选字段
    """
    OCTET_STRING_LENGTH = 32
    BIT_STRING_LENGTH = 64

    def __init__(self, targets: list, max_recur_depth=0, seed=20, optional=True) -> None:
        self.seed = seed
        random.seed(seed)
        self.targets = targets
        self.optional = optional
        self.bb = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message

        self.recursif_fields = list(
            map(lambda x: x[-1], get_recursif_field_paths(self.targets)))
        self.max_recur_depth = max_recur_depth

        # 对每个目标字段，获取到达该字段的路径及所需的 CHOICE 选择序列
        _, _, choice_paths = get_choices(self.bb, targets=self.targets)

        # 收集所有 CHOICE 路径
        self.choice_paths = [(choices[:-1], paths[1:])
                             for (choices, paths) in choice_paths]

        self.choice_index = 0

        tmp = []
        for (choices, full_path) in self.choice_paths:
            while '_item_' in full_path:
                full_path.remove('_item_')
            full_path = [
                item for item in full_path if not item.startswith('_cont_')]
            tmp += [(choices, full_path)]

        self.choice_paths = tmp
        self.current_choice_path = []
        self.found_paths = set()
        self.choices = set()
        self.next_choice_path_generator = self._get_next_choice_path_generator()

    def add_to_found(self, path: list) -> None:
        """
        将路径添加到已发现集合，避免重复生成

        Args:
            path: 要添加的路径
        """
        self.found_paths.add(tuple(path))

    def reset_found(self) -> None:
        """重置已发现路径集合和 CHOICE 集合"""
        self.found_paths = set()
        self.choices = set()
        self.choice_index = 0

    def _get_next_choice_path_generator(self):
        """
        生成器：产出下一个未探索的 CHOICE 路径。
        使用 round-robin 方式遍历所有 CHOICE 路径，跳过已探索的。
        当所有路径都已探索时，自动重置并重新遍历。

        Yields:
            list: 连续的 CHOICE 选择列表
        """
        n = len(self.choice_paths)
        while True:
            self.choice_index = (self.choice_index + 1) % n
            choices, full_path = [], []
            attempts = 0
            while True:
                choices, full_path = self.choice_paths[self.choice_index - 1]

                if tuple(full_path) not in self.found_paths and tuple(choices) not in self.choices:
                    self.choices.add(tuple(choices))
                    break
                self.choice_index = (self.choice_index + 1) % n
                attempts += 1
                if attempts >= n:
                    # 所有路径均已探索，重置后重新开始
                    self.found_paths.clear()
                    self.choices.clear()
                    attempts = 0

            yield choices.copy()

    def _loop_IE(self, bb, choice_path=[], curr_path=[], targets=[], recur_depth=0):
        """
        递归遍历 ASN.1 结构，生成每个元素的值

        对不同 ASN.1 类型（SEQUENCE, CHOICE, INTEGER, OCTET STRING, BIT STRING,
        SEQUENCE OF 等）采用相应的生成策略。

        Args:
            bb:           当前 ASN.1 元素
            choice_path:  CHOICE 选择路径
            curr_path:    当前在消息结构中的路径
            targets:      目标字段类型列表
            recur_depth:  当前递归深度

        Returns:
            (generated_value, mutation_paths, optional_paths) 三元组
        """
        if bb._name == 'DL-DCCH-Message':
            assert len(self.current_choice_path) == 0
            choice_path = self.next_choice_path_generator.__next__()

        if bb.TYPE == 'NULL':
            return 0, [], []

        if bb.TYPE == 'SEQUENCE':
            logging.debug(f'SEQUENCE: {bb._name}, path={curr_path}')

            if bb == {}:
                logging.error('Empty sequence')

            one_ie = {}
            optional_paths = []
            tot_optional_paths = []
            tot_mutation_paths = []

            if bb._opt:
                optional_paths.append(curr_path)

            items = [t[0] for t in list(bb._cont.items())]
            for ie_name in items:
                if ie_name in bb._root_mand or self.optional:
                    gen, rec_mutation_paths, rec_optional_paths = self._loop_IE(
                        bb._cont[ie_name], choice_path.copy(), [*curr_path, ie_name],
                        targets, recur_depth=recur_depth)

                    one_ie[ie_name] = gen
                    tot_optional_paths += rec_optional_paths
                    tot_mutation_paths += rec_mutation_paths

            return one_ie, [l for l in tot_mutation_paths if l], optional_paths + tot_optional_paths

        if bb.TYPE == 'CHOICE':
            logging.debug(f'CHOICE: {bb._name}, path={curr_path}')

            options = list(bb._cont.keys())
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)

            if len(choice_path) == 0:
                next_ie = random.choice(options)
            else:
                next_ie = choice_path[0]

            if next_ie not in options:
                next_ie = random.choice(options)
            elif len(choice_path) > 0:
                choice_path.pop(0)

            gen, rec_mutation_paths, rec_optional_paths = self._loop_IE(
                bb._cont[next_ie], choice_path.copy(), [*curr_path, next_ie],
                targets, recur_depth=recur_depth)
            rec_mutation_paths = [p for p in rec_mutation_paths if p]

            return (next_ie, gen), rec_mutation_paths, optional_paths + rec_optional_paths

        if bb.TYPE == 'INTEGER':
            ie_range = bb._const_val.root[0]
            mutation_paths = []
            if type(ie_range) == int:
                ie_lb = ie_range
                ie_ub = ie_range
            else:
                ie_lb = ie_range.lb
                ie_ub = ie_range.ub

            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)

            r = ie_ub - ie_lb + 1
            if r & (r - 1) != 0 and Fields.INTEGER in targets:
                mutation_paths.append(curr_path)

            return random.randint(ie_lb, ie_ub), mutation_paths, optional_paths

        if bb.TYPE == 'ENUMERATED':
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            return random.choice(bb._root), [], optional_paths

        if bb.TYPE == 'BOOLEAN':
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            return random.choice([True, False]), [], optional_paths

        if bb.TYPE == 'OCTET STRING':
            logging.debug(f'OCTET STRING: {bb._name}, path={curr_path}')

            mutation_path = []
            optional_paths = []

            if bb._opt:
                optional_paths.append(curr_path)

            if bb._const_cont is not None:
                if bb._name in self.recursif_fields:
                    if recur_depth == self.max_recur_depth:
                        logging.debug(f'Max recursion depth reached for {bb._name}')
                        return b'a', [], optional_paths
                    recur_depth = recur_depth + 1

                container = RRCLTE_R17.GLOBAL.MOD['EUTRA-RRC-Definitions'][
                    bb._const_cont.get_type_list()[0]]

                ie, rec_mutation_paths, rec_optional_paths = self._loop_IE(
                    container, choice_path.copy(), curr_path, targets,
                    recur_depth=recur_depth)

                embedded_mutation_paths = []
                for m in rec_mutation_paths:
                    embedded_mutation_paths.append(
                        curr_path + ['*', bb._const_cont.get_type_list()[0]] + m[len(curr_path):])

                for o in rec_optional_paths:
                    optional_paths.append(
                        curr_path + ['*', bb._const_cont.get_type_list()[0]] + o[len(curr_path):])

                container.set_val(ie)

                if Fields.OCTET_STRING in targets:
                    mutation_path = curr_path

                return bytes.fromhex(container.to_uper().hex()), \
                    [mutation_path] + embedded_mutation_paths, optional_paths

            if Fields.OCTET_STRING in targets:
                mutation_path = curr_path

            if bb._const_sz is not None:
                oct_str_len = random.randint(bb._const_sz.lb, bb._const_sz.ub)
                if bb._const_sz.lb == bb._const_sz.ub:
                    mutation_path = []
            else:
                oct_str_len = self.OCTET_STRING_LENGTH

            return bytes(random.getrandbits(8) for _ in range(oct_str_len)), \
                [mutation_path], optional_paths

        if bb.TYPE == 'BIT STRING':
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)

            if bb._const_cont is not None:
                logging.debug('Found not None continuation for BIT STRING')
                exit(0)

            mutation_path = []
            if Fields.BIT_STRING in targets:
                mutation_path = curr_path

            if bb._const_sz is not None:
                bit_str_len = random.randint(bb._const_sz.lb, bb._const_sz.ub)
                if bb._const_sz.lb == bb._const_sz.ub:
                    mutation_path = []
            else:
                bit_str_len = self.BIT_STRING_LENGTH

            return (random.getrandbits(bit_str_len), bit_str_len), [mutation_path], optional_paths

        if bb.TYPE == 'SEQUENCE OF':
            if bb._name == '_item_' and bb._tr is not None:
                curr_path = curr_path + ['^', bb._tr._name]

            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)

            temp = []
            mutation_paths = []

            n_elem = bb._const_sz.lb
            if bb._const_sz.lb == bb._const_sz.ub:
                n_elem = bb._const_sz.lb
            else:
                n_elem = bb._const_sz.lb + 1

            for i in range(n_elem):
                gen, rec_mutation_paths, rec_optional_paths = self._loop_IE(
                    bb._cont,
                    choice_path.copy(),
                    [*curr_path, '__elem__', i],
                    targets,
                    recur_depth=recur_depth)

                temp.append(gen)
                mutation_paths += rec_mutation_paths
                optional_paths += rec_optional_paths

            mutation_path = None
            if Fields.SEQOF in targets and bb._const_sz.lb != bb._const_sz.ub:
                r = bb._const_sz.ub - bb._const_sz.lb + 1
                if r & (r - 1) != 0:
                    mutation_path = curr_path

            return temp, [p for p in [mutation_path] + mutation_paths if p], optional_paths

    def generate_packet(self):
        """
        生成一个合法的 RRC DL-DCCH-Message 数据包

        遍历 ASN.1 结构，填充所有必需字段和（可选的）可选字段，
        使用 UPER 编码输出。

        Returns:
            uper_bytes:      UPER 编码的数据包字节
            result:          字典格式的生成结果
            mutation_paths:  可用于后续处理的路径列表
            optional_paths:  可选字段路径列表
        """
        gen_result = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
        result, mutation_paths, optional_paths = self._loop_IE(
            self.bb, targets=self.targets)

        logging.debug(f'Generated packet result: {result}')
        logging.debug(f'Mutation paths: {mutation_paths}')
        logging.debug(f'Optional paths: {optional_paths}')

        try:
            gen_result.set_val(result)
        except Exception as e:
            logging.error(f"Failed to set packet value: {e}")
            os._exit(0)

        logging.debug(f'Generated UPER hex: {gen_result.to_uper().hex()}')
        return gen_result.to_uper(), result, mutation_paths, optional_paths

    def generate_packet_hex(self) -> str:
        """
        生成合法 RRC 数据包并返回十六进制字符串

        Returns:
            str: 十六进制格式的 UPER 编码数据包
        """
        uper_bytes, _, _, _ = self.generate_packet()
        return uper_bytes.hex()

    def get_unique_paths(self, paths):
        """
        从路径列表中提取唯一路径（去除整数索引）

        Args:
            paths: 路径列表

        Returns:
            set: 唯一路径集合
        """
        unique_paths = set()
        for path in paths:
            unique_paths.add(tuple(
                [x for x in path if not isinstance(x, int)]))
        return unique_paths
