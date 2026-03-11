"""
5G NR INTEGER 字段变异工具

接口与 4G 版本完全一致，仅协议定义替换为 NR RRC。
"""
import math
import random
from typing import List, Tuple, Optional

from pycrate.pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT  = True

from bishe.pycrate_asn1obj.nr_5g import RRCNR

from .mutation_utils import bytes_to_bit_str, bit_str_to_bytes


def _lbs(field) -> int:
    """计算 INTEGER 字段的长度头比特数"""
    lb = field._const_val.lb
    ub = field._const_val.ub
    return math.floor(math.log2(ub - lb)) + 1


def _field_bits(field) -> str:
    """返回 INTEGER 字段在 UPER 中的比特串"""
    lb  = field._const_val.lb
    val = field.get_val()
    lbs = _lbs(field)
    return format(val - lb, f"0{lbs}b")


def _find_all(pkt_bits: str, tgt: str) -> set:
    s, idxs = 0, set()
    while True:
        i = pkt_bits.find(tgt, s)
        if i == -1:
            break
        idxs.add(i)
        s = i + 1
    return idxs


def _find_index(pkt_bits: str, fld_bits: str, path: list, packet) -> int:
    """在数据包比特流中定位 INTEGER 字段位置"""
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("INTEGER 字段未在数据包比特流中找到")
    if len(idxs) == 1:
        return idxs.pop()

    fld     = packet.get_at(path)
    lb      = fld._const_val.lb
    ub      = fld._const_val.ub
    old_val = packet.get_val_at(path)
    new_val = old_val
    while new_val == old_val:
        new_val = random.randint(lb, ub)
    packet.set_val_at(path, new_val)
    fld.set_val(new_val)
    nbits = _field_bits(packet.get_at(path))
    npkt  = bytes_to_bit_str(packet.to_uper())
    idxs  = _find_all(npkt, nbits) & idxs
    packet.set_val_at(path, old_val)
    fld.set_val(old_val)
    if not idxs:
        raise ValueError("INTEGER 歧义消除失败")
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]


def _integer_muts(field) -> List[Tuple[str, int]]:
    """INTEGER 3 条变异"""
    lb      = field._const_val.lb
    ub      = field._const_val.ub
    lbs_    = _lbs(field)

    rand_val     = random.randint(lb, ub)
    rand_bits    = format(rand_val - lb, f"0{lbs_}b")

    max_repr     = 2**lbs_ - 1
    maxrepr_bits = format(max_repr, f"0{lbs_}b")

    overflow     = ub - lb + 1
    overflow_bits = format(overflow, f"0{lbs_}b")

    delta = 0
    return [
        (rand_bits,     delta),
        (maxrepr_bits,  delta),
        (overflow_bits, delta),
    ]


def mutate_integer_5g(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> List[Tuple[str, str, List[str]]]:
    """
    对 5G NR RRC 消息中的 INTEGER 字段执行比特流级变异。

    参数：
        uper_hex:     合法消息的 UPER 十六进制编码
        message_type: 消息类型名称
        target_path:  目标字段路径列表
        seed:         随机数种子（可选）

    返回：
        [(mutated_uper_hex, message_type, target_path), ...] 列表，共 3 条
    """
    if seed is not None:
        random.seed(seed)

    pkt = RRCNR.NR_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    fld = pkt.get_at(target_path)
    fld.set_val(pkt.get_val_at(target_path))

    if fld.TYPE != "INTEGER":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 INTEGER")

    bit_muts = _integer_muts(fld)

    pkt_bits = bytes_to_bit_str(pkt.to_uper())
    fld_bits = _field_bits(fld)
    fld_idx  = _find_index(pkt_bits, fld_bits, target_path, pkt)

    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for (mut_bits, _delta) in bit_muts:
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path))
    return results
