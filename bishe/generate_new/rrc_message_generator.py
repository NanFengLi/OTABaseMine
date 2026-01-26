"""
RRC Message Generator (with pycrate)
------------------------------------
生成RRC消息、target_path、choice_path和target字段类型。
依赖：pycrate, releaseLTE_R17（需用户提供ASN.1定义模块）
"""
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if project_root not in sys.path:
    sys.path.append(project_root)


artifact_rrc_path = os.path.join(project_root, "artifact/test-case-generator")
if artifact_rrc_path not in sys.path:
    sys.path.append(artifact_rrc_path)
import random
import logging
from enum import Enum
from rrc.rrc_choices import get_choices
from rrc.rrc_fields import Fields
from rrc.rrc_stats import get_recursif_field_paths
from rrc.releaseLTE_R17 import RRCLTE_R17

class RRCMessageGenerator:
    OCTET_STRING_LENGTH = 32
    BIT_STRING_LENGTH = 64

    def __init__(self, targets, max_recur_depth=0, seed=20, optional=True):
        self.targets = targets
        self.optional = optional
        self.bb = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
        self.recursif_fields = list(
            map(lambda x: x[-1], get_recursif_field_paths(self.targets)))
        self.max_recur_depth = max_recur_depth
        random.seed(seed)
        _, _, choice_paths = get_choices(self.bb, targets=self.targets)
        self.choice_paths = [(choices[:-1], paths[1:]) for (choices, paths) in choice_paths]
        tmp = []
        for (choices, full_path) in self.choice_paths:
            while ('_item_' in full_path):
                full_path.remove('_item_')
            full_path = [item for item in full_path if not item.startswith('_cont_')]
            tmp += [(choices, full_path)]
        self.choice_paths = tmp
        self.choice_index = 0
        self.found_paths = set()
        self.choices = set()
        self.next_choice_path_generator = self.get_next_choice_path_generator()

    def get_next_choice_path_generator(self):
        while True:
            self.choice_index = (self.choice_index + 1)
            self.choice_index = self.choice_index % len(self.choice_paths)
            choices, full_path = [], []
            while True:
                choices, full_path = self.choice_paths[self.choice_index - 1]
                if tuple(full_path) not in self.found_paths and tuple(choices) not in self.choices:
                    self.choices.add(tuple(choices))
                    break
                self.choice_index += 1
            yield choices.copy()

    def add_to_found(self, path):
        self.found_paths.add(tuple(path))

    def reset_found(self):
        self.found_paths = set()
        self.choices = set()
        self.choice_index = 0

    def loop_IE(self, bb, choice_path=[], curr_path=[], targets=[], recur_depth=0):
        if bb._name == 'DL-DCCH-Message':
            assert len(choice_path) == 0
            choice_path = next(self.next_choice_path_generator)
        if (bb.TYPE == 'NULL'):
            return 0, [], []
        if (bb.TYPE == 'SEQUENCE'):
            one_ie = {}
            optional_paths = []
            tot_optional_paths = []
            tot_mutation_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            items = [t[0] for t in list(bb._cont.items())]
            for ie_name in items:
                if ie_name in bb._root_mand or self.optional:
                    gen, rec_mutation_paths, rec_optional_paths = self.loop_IE(
                        bb._cont[ie_name], choice_path.copy(), [*curr_path, ie_name], targets, recur_depth=recur_depth)
                    one_ie[ie_name] = gen
                    tot_optional_paths += rec_optional_paths
                    tot_mutation_paths += rec_mutation_paths
            return one_ie, [l for l in tot_mutation_paths if l], optional_paths + tot_optional_paths
        if (bb.TYPE == 'CHOICE'):
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
            rand_ie = next_ie
            gen, rec_mutation_paths, rec_optional_paths = self.loop_IE(
                bb._cont[rand_ie], choice_path.copy(), [*curr_path,  rand_ie], targets, recur_depth=recur_depth)
            rec_mutation_paths = [p for p in rec_mutation_paths if p]
            return (rand_ie, gen), rec_mutation_paths, optional_paths + rec_optional_paths
        if (bb.TYPE == 'INTEGER'):
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
        if (bb.TYPE == 'ENUMERATED'):
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            return random.choice(bb._root), [], optional_paths
        if (bb.TYPE == 'BOOLEAN'):
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            return random.choice([True, False]), [], optional_paths
        if (bb.TYPE == 'OCTET STRING'):
            mutation_path = []
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            if bb._const_cont is not None:
                if bb._name in self.recursif_fields:
                    if recur_depth == self.max_recur_depth:
                        return b'a', [], optional_paths
                    recur_depth = recur_depth + 1
                container = RRCLTE_R17.GLOBAL.MOD['EUTRA-RRC-Definitions'][bb._const_cont.get_type_list()[0]]
                ie, rec_mutation_paths, rec_optional_paths = self.loop_IE(
                    container, choice_path.copy(), curr_path, targets, recur_depth=recur_depth)
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
                return bytes.fromhex(container.to_uper().hex()), [mutation_path] + embedded_mutation_paths, optional_paths
            if Fields.OCTET_STRING in targets:
                mutation_path = curr_path
            if (bb._const_sz != None):
                oct_str_len = random.randint(bb._const_sz.lb, bb._const_sz.ub)
                if bb._const_sz.lb == bb._const_sz.ub:
                    mutation_path = []
            else:
                oct_str_len = self.OCTET_STRING_LENGTH
            return bytes(random.getrandbits(8) for _ in range(oct_str_len)), [mutation_path], optional_paths
        if (bb.TYPE == 'BIT STRING'):
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            if bb._const_cont is not None:
                exit(0)
            mutation_path = []
            if Fields.BIT_STRING in targets:
                mutation_path = curr_path
            if (bb._const_sz != None):
                bit_str_len = random.randint(bb._const_sz.lb, bb._const_sz.ub)
                if bb._const_sz.lb == bb._const_sz.ub:
                    mutation_path = []
            else:
                bit_str_len = self.BIT_STRING_LENGTH
            return (random.getrandbits(bit_str_len), bit_str_len), [mutation_path], optional_paths
        if (bb.TYPE == 'SEQUENCE OF'):
            if bb._name == '_item_' and bb._tr is not None:
                curr_path = curr_path + ['^', bb._tr._name]
            optional_paths = []
            if bb._opt:
                optional_paths.append(curr_path)
            temp = []
            mutation_paths = []
            n_elem = random.randint(bb._const_sz.lb, bb._const_sz.ub)
            n_elem = bb._const_sz.lb
            if bb._const_sz.lb == bb._const_sz.ub:
                n_elem = bb._const_sz.lb
            else:
                n_elem = bb._const_sz.lb + 1
            for i in range(n_elem):
                gen, rec_mutation_paths, rec_optional_paths = self.loop_IE(
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
        gen_result = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
        result, mutation_paths, optional_paths = self.loop_IE(
            self.bb, targets=self.targets)
        try:
            gen_result.set_val(result)
        except Exception as e:
            logging.error("error: ", e)
            import os
            os._exit(0)
        return {
            'rrc_message': gen_result.to_uper(),
            'target_path': mutation_paths,
            'choice_path': optional_paths,
            'target_field_type': self.targets
        }

from fields import Fields
from rrc_message_generator_core import RRCMessageGenerator

if __name__ == "__main__":
    targets = [Fields.OCTET_STRING, Fields.INTEGER]
    generator = RRCMessageGenerator(targets)
    with open("output.txt", "w") as f:
        f.write(f"共发现{len(generator.choice_paths)}条可选路径\n")
        for idx, (choices, path) in enumerate(generator.choice_paths):
            result = generator.generate_packet()
            msg = (f"--- 第{idx+1}条路径 ---\n"
                   f"RRC消息: {result['rrc_message'].hex()}\n"
                   f"mutation_paths: {result['target_path']}\n"
                   f"optional_paths: {result['choice_path']}\n"
                   f"target字段类型: {result['target_field_type']}\n\n")
            f.write(msg)
