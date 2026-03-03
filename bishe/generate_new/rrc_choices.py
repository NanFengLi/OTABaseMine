"""
RRC CHOICE 路径分析模块

分析 ASN.1 语法树，计算到达目标字段所需的 CHOICE 路径序列。
用于指导生成器在遍历 ASN.1 结构时选择正确的分支以覆盖目标字段。

从 OTABase artifact/test-case-generator/rrc/rrc_choices.py 抽取。
"""
from pycrate_asn1rt.codecs import *
from pycrate_asn1rt.setobj import *
from pycrate_asn1rt.dictobj import *
from pycrate_asn1rt.refobj import *
from pycrate_asn1rt.err import *
from pycrate_asn1rt.utils import *
from pycrate_asn1rt import *

from bishe.generate_new.releaseLTE_R17 import RRCLTE_R17
from bishe.generate_new.rrc_fields import Fields

import logging


def get_choices(sel, path=[], depth=0, targets=[Fields.OCTET_STRING]) -> tuple:
    """
    计算到达目标字段的所有路径及到达目标字段所需的 CHOICE 选择序列。

    递归遍历 ASN.1 语法树，记录每个 CHOICE 节点的选择，
    以及到达每个目标字段类型（如 OCTET_STRING、INTEGER）的完整路径。

    Args:
        sel: 当前 ASN.1 对象
        path: 当前路径
        depth: 当前深度
        targets: 目标字段类型列表

    Returns:
        num: CHOICE 节点数量
        recur: 导致递归的路径列表
        choice_paths: [(choices, path)] CHOICE 选择和目标路径的列表
    """
    num, recur = 0, []
    choice_paths = []

    if not hasattr(sel, '_proto_recur'):
        root = True
        sel._proto_recur = [id(sel)]
        sel._proto_path = []
    else:
        root = False

    if sel.TYPE in (TYPE_SEQ, TYPE_SET, TYPE_CLASS):
        for (ident, Comp) in sel._cont.items():
            if id(Comp) in sel._proto_recur:
                recur_path = sel._proto_path + [ident]
                logging.debug('[+] recursion detected: %s, at path %r'
                              % (Comp._name, recur_path))
                recur.append(recur_path)
            else:
                Comp._proto_recur = sel._proto_recur + [id(Comp)]
                Comp._proto_path = sel._proto_path + [ident]
                comp_num, comp_recur, c_paths = get_choices(
                    Comp, path + [sel._name], depth, targets)
                del Comp._proto_recur, Comp._proto_path
                num += comp_num
                recur.extend(comp_recur)
                choice_paths.extend(c_paths)

    elif sel.TYPE == TYPE_CHOICE:
        weights = {}

        for (ident, Comp) in sel._cont.items():
            if id(Comp) in sel._proto_recur:
                recur_path = sel._proto_path + [ident]
                logging.debug('[+] recursion detected: %s, at path %r'
                              % (Comp._name, recur_path))
                recur.append(recur_path)
            else:
                Comp._proto_recur = sel._proto_recur + [id(Comp)]
                Comp._proto_path = sel._proto_path + [ident]
                comp_num, comp_recur, c_paths = get_choices(
                    Comp, path + [sel._name], depth + 1, targets)
                for (choices, full_path) in c_paths:
                    choice_paths.append(([ident] + choices, full_path))

                del Comp._proto_recur, Comp._proto_path
                weights[ident] = (comp_num, Comp)
                num += comp_num
                recur.extend(comp_recur)

        c = 0
        if num == 0:
            for (ident, (comp_num, Comp)) in weights.items():
                weights[ident] = (1 / len(weights), Comp)
                Comp.weight = weights[ident][0]
        else:
            for (ident, (comp_num, Comp)) in weights.items():
                if comp_num == 0:
                    c += 1
            for (ident, (comp_num, Comp)) in weights.items():
                if comp_num == 0:
                    Comp.weight = 0
                else:
                    weights[ident] = (1 / (len(weights) - c), Comp)
                    Comp.weight = 1 / (len(weights) - c)

        num += 0

    # SEQUENCE OF 或 SET OF
    elif sel.TYPE in (TYPE_SEQ_OF, TYPE_SET_OF):
        Comp = sel._cont
        if id(Comp) in sel._proto_recur:
            recur_path = sel._proto_path + [None]
            logging.debug('[+] recursion detected: %s, at path %r'
                          % (Comp._name, recur_path))
            recur.append(recur_path)
        else:
            Comp._proto_recur = sel._proto_recur + [id(Comp)]
            Comp._proto_path = sel._proto_path + [None]
            comp_num, comp_recur, c_paths = get_choices(
                Comp, path + [sel._name], depth, targets)
            choice_paths = c_paths
            del Comp._proto_recur, Comp._proto_path
            num += comp_num
            recur.extend(comp_recur)

        if sel.TYPE in (TYPE_SEQ_OF) and Fields.SEQOF in targets \
                and sel._const_sz.lb != sel._const_sz.ub:
            choice_paths = choice_paths + [([sel._name], path + [sel._name])]
            num += 1

    # 带有内嵌内容的 BIT STRING / OCTET STRING
    elif sel.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR) and sel._const_cont:
        Comp = sel._const_cont
        if id(Comp) in sel._proto_recur:
            recur_path = sel._proto_path + [None]
            logging.debug('[+] recursion detected: %s, at path %r'
                          % (Comp._name, recur_path))
            recur.append(recur_path)
        else:
            Comp._proto_recur = sel._proto_recur + [id(Comp)]
            Comp._proto_path = sel._proto_path + [None]
            comp_num, comp_recur, c_paths = get_choices(
                Comp, path + [sel._name] + [sel._const_cont.get_type_list()[0]], depth, targets)
            del Comp._proto_recur, Comp._proto_path
            num += comp_num
            choice_paths = c_paths
            recur.extend(comp_recur)

        if (sel.TYPE == TYPE_BIT_STR and Fields.BIT_STRING in targets) \
                or (sel.TYPE == TYPE_OCT_STR and Fields.OCTET_STRING in targets):
            num += 1
            choice_paths = choice_paths + [([sel._name], path + [sel._name])]
            if sel._const_sz is not None and sel._const_sz.lb == sel._const_sz.ub:
                num -= 1
                choice_paths = []

    # 不带内嵌内容的 BIT STRING / OCTET STRING
    elif sel.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR):
        if (sel.TYPE == TYPE_BIT_STR and Fields.BIT_STRING in targets) \
                or (sel.TYPE == TYPE_OCT_STR and Fields.OCTET_STRING in targets):
            num += 1
            choice_paths = [([sel._name], path + [sel._name])]
            if sel._const_sz is not None and sel._const_sz.lb == sel._const_sz.ub:
                num -= 1
                choice_paths = []

    elif sel.TYPE in TYPE_INT:
        ie_range = sel._const_val.root[0]
        if type(ie_range) == int:
            ie_lb = ie_range
            ie_ub = ie_range
        else:
            ie_lb = ie_range.lb
            ie_ub = ie_range.ub

        r = ie_ub - ie_lb + 1
        if r & (r - 1) != 0 and Fields.INTEGER in targets:
            choice_paths = [([sel._name], path + [sel._name])]
            num += 1

    else:
        assert (sel.TYPE in TYPES_BASIC + TYPES_EXT)
        num = 0
        choice_paths = []

    if root:
        del sel._proto_recur, sel._proto_path
        return num, recur, choice_paths
    return num, recur, choice_paths
