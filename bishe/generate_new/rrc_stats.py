"""
RRC 统计分析模块

分析 ASN.1 语法树的结构，统计目标字段数量、递归路径、可变异路径等。
用于生成器的初始化和覆盖率计算。

从 OTABase artifact/test-case-generator/rrc/rrc_stats.py 抽取。
"""
from bishe.generate_new.releaseLTE_R17 import RRCLTE_R17

from pycrate_asn1rt import *
from pycrate_asn1rt.utils import *
from pycrate_asn1rt.err import *
from pycrate_asn1rt.refobj import *
from pycrate_asn1rt.dictobj import *
from pycrate_asn1rt.setobj import *
from pycrate_asn1rt.codecs import *

from .rrc_fields import Fields

import logging


def add_dicts(dict1, dict2):
    """合并两个嵌套字典，数值累加"""
    result = {}
    for key in set(dict1.keys()) | set(dict2.keys()):
        if key in dict1 and key in dict2:
            if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                result[key] = add_dicts(dict1[key], dict2[key])
            else:
                result[key] = dict1[key] + dict2[key]
        elif key in dict1:
            result[key] = dict1[key]
        else:
            result[key] = dict2[key]
    return result


def get_stats(sel, w_open=True, w_opt=True, targets=[], curr_path=[]):
    """
    分析 ASN.1 语法树的复杂度和目标字段分布。

    Args:
        sel:        当前 ASN.1 对象
        w_open:     是否检查 OPEN 类型的潜在内容
        w_opt:      是否检查可选字段
        targets:    目标字段类型列表
        curr_path:  当前路径

    Returns:
        recur:          导致递归的路径列表
        stats:          各目标字段类型的 bound/unbound 统计
        mutation_paths: 可用于生成/变异的路径列表
        ies:            语法中所有 IE 名称集合
    """
    stats = {}
    ies = set()

    for t in targets:
        stats[t] = {'bound': 0, 'unbound': 0}

    recur, mutation_paths = [], []

    if not hasattr(sel, '_proto_recur'):
        root = True
        sel._proto_recur = [id(sel)]
        sel._proto_path = []
    else:
        root = False

    if sel.TYPE in (TYPE_CHOICE, TYPE_SEQ, TYPE_SET, TYPE_CLASS):
        for (ident, Comp) in sel._cont.items():
            if id(Comp) in sel._proto_recur:
                recur_path = sel._proto_path
                recur.append(recur_path)
            elif w_opt or not hasattr(sel, '_root_mand') \
                    or Comp._name in sel._root_mand:
                path = curr_path
                next_path = path + [ident]

                Comp._proto_recur = sel._proto_recur + [id(Comp)]
                Comp._proto_path = sel._proto_path + [ident]
                comp_recur, comp_stats, comp_mut, comp_ies = get_stats(
                    Comp, w_open, w_opt, targets, next_path)
                del Comp._proto_recur, Comp._proto_path
                stats = add_dicts(stats, comp_stats)
                recur.extend(comp_recur)
                mutation_paths += comp_mut
                ies = ies.union(comp_ies)

    # SEQUENCE OF / SET OF
    elif sel.TYPE in (TYPE_SEQ_OF, TYPE_SET_OF):
        Comp = sel._cont
        if id(Comp) in sel._proto_recur:
            recur_path = sel._proto_path + [None]
            recur.append(recur_path)
        else:
            next_path = curr_path + [Comp._name]
            if Comp._name == '_item_' and sel._tr is not None:
                next_path = curr_path + ['^', sel._tr._name]

            Comp._proto_recur = sel._proto_recur + [id(Comp)]
            Comp._proto_path = sel._proto_path + [None]
            comp_recur, comp_stats, comp_mut, comp_ies = get_stats(
                Comp, w_open, w_opt, targets, next_path)
            del Comp._proto_recur, Comp._proto_path
            stats = add_dicts(stats, comp_stats)
            recur.extend(comp_recur)
            mutation_paths += comp_mut
            ies = ies.union(comp_ies)

        if sel.TYPE in (TYPE_SEQ_OF) and Fields.SEQOF in targets and \
                sel._const_sz.lb != sel._const_sz.ub:
            mutation_paths.append(curr_path)
            stats[Fields.SEQOF]['bound'] += 1

    # 带内嵌内容的 OCTET STRING / BIT STRING
    elif sel.TYPE in (TYPE_BIT_STR, TYPE_OCT_STR) and sel._const_cont:
        Comp = sel._const_cont
        if id(Comp) in sel._proto_recur:
            recur_path = sel._proto_path + [None]
            recur.append(recur_path)
        else:
            Comp._proto_recur = sel._proto_recur + [id(Comp)]
            Comp._proto_path = sel._proto_path + [None]
            comp_recur, comp_stats, comp_mut, comp_ies = get_stats(
                Comp, w_open, w_opt, targets,
                curr_path + [Comp._name])
            del Comp._proto_recur, Comp._proto_path
            stats = add_dicts(stats, comp_stats)
            recur.extend(comp_recur)
            mutation_paths += comp_mut
            ies = ies.union(comp_ies)

        if sel.TYPE is TYPE_OCT_STR and Fields.OCTET_STRING in targets:
            if sel._const_sz is not None and sel._const_sz.lb != sel._const_sz.ub:
                mutation_paths.append(curr_path)
                stats[Fields.OCTET_STRING]['bound'] += 1
            elif sel._const_sz is None:
                mutation_paths.append(curr_path)
                stats[Fields.OCTET_STRING]['unbound'] += 1

        if sel.TYPE is TYPE_BIT_STR and Fields.BIT_STRING in targets:
            if sel._const_sz is not None and sel._const_sz.lb != sel._const_sz.ub:
                mutation_paths.append(curr_path)
                stats[Fields.BIT_STRING]['bound'] += 1
            elif sel._const_sz is None:
                mutation_paths.append(curr_path)
                stats[Fields.BIT_STRING]['unbound'] += 1

    # 不带内嵌内容的 OCTET STRING
    elif sel.TYPE is TYPE_OCT_STR and Fields.OCTET_STRING in targets:
        if sel._const_sz is not None and sel._const_sz.lb != sel._const_sz.ub:
            mutation_paths.append(curr_path)
            stats[Fields.OCTET_STRING]['bound'] += 1
        elif sel._const_sz is None:
            mutation_paths.append(curr_path)
            stats[Fields.OCTET_STRING]['unbound'] += 1

    # 不带内嵌内容的 BIT STRING
    elif sel.TYPE is TYPE_BIT_STR and Fields.BIT_STRING in targets:
        if sel._const_sz is not None and sel._const_sz.lb != sel._const_sz.ub:
            mutation_paths.append(curr_path)
            stats[Fields.BIT_STRING]['bound'] += 1
        elif sel._const_sz is None:
            mutation_paths.append(curr_path)
            stats[Fields.BIT_STRING]['unbound'] += 1

    # INTEGER
    elif sel.TYPE is TYPE_INT and Fields.INTEGER in targets:
        ie_range = sel._const_val.root[0]
        if type(ie_range) == int:
            ie_lb = ie_range
            ie_ub = ie_range
        else:
            ie_lb = ie_range.lb
            ie_ub = ie_range.ub

        r = ie_ub - ie_lb + 1
        if r & (r - 1) != 0 and Fields.INTEGER in targets:
            mutation_paths.append(curr_path)
            stats[Fields.INTEGER]['bound'] += 1
    else:
        assert (sel.TYPE in TYPES_BASIC + TYPES_EXT)

    if root:
        del sel._proto_recur, sel._proto_path
    ies.add(sel._name)
    return recur, stats, mutation_paths, ies


def sum_stats(targets, stats):
    """汇总各目标字段类型的统计数"""
    total = 0
    for t in targets:
        total += stats[t]['bound'] + stats[t]['unbound']
    return total


def get_target_field_count(targets, w_recur=False):
    """
    获取 DL-DCCH-Message 中目标字段的总数量。

    Args:
        targets: 目标字段类型列表
        w_recur: 是否计入递归路径中的字段

    Returns:
        int: 目标字段数量
    """
    message = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
    recur, stats, _, _ = get_stats(
        message, w_opt=True, targets=targets)

    if not w_recur and Fields.OCTET_STRING in targets:
        stats[Fields.OCTET_STRING]['unbound'] -= len(recur)
    return sum_stats(targets, stats)


def get_recursif_field_paths(targets, optional=True):
    """
    获取所有会导致递归的字段路径。

    Args:
        targets: 目标字段类型列表
        optional: 是否包含可选字段

    Returns:
        list: 过滤后的递归路径列表
    """
    message = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
    recur = get_stats(
        message, w_opt=optional, targets=targets)[0]
    filtered_recur = []
    for r in recur:
        filtered_recur.append(list(filter(lambda x: x is not None, r)))
    return filtered_recur


def get_total_ie_count():
    """
    获取 DL-DCCH-Message 中所有 IE 的总数量。

    Returns:
        int: IE 总数
    """
    message = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
    _, _, _, ies = get_stats(
        message, w_opt=True, targets=[])
    return len(ies)


def get_stats_mutation_paths(targets, w_recur=False, w_opt=True):
    """
    获取所有可用于生成的目标路径。

    Args:
        targets: 目标字段类型列表
        w_recur: 是否考虑递归
        w_opt: 是否包含可选字段

    Returns:
        set: IE 名称集合
    """
    message = RRCLTE_R17.EUTRA_RRC_Definitions.DL_DCCH_Message
    return get_stats(
        message, w_opt=w_opt, targets=targets)[-1]
