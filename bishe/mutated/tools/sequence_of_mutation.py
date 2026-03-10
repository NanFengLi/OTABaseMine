"""
SEQUENCE OF 字段变异工具

接口：
  输入  uper_hex, message_type, target_path
  输出  变异后的 (uper_hex, message_type, target_path) 列表

完全移植自 OTABase rrc_fuzzer.py::mutate_rrc_seqof_field()
注意：只修改长度头比特，元素内容不变（delta 始终为 0）。
"""
import math
import random
from typing import List, Tuple, Optional

from pycrate.pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT  = True

from bishe.pycrate_asn1obj.eutran_4g import RRCLTE

from .mutation_utils import (
    bytes_to_bit_str, bit_str_to_bytes,
)

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _lbs(field) -> int:
    """计算 SEQUENCE OF 长度头所需的比特数（同 OTABase）"""
    max_len = field._const_sz.ub - field._const_sz.lb
    return math.floor(math.log2(max_len)) + 1


def _field_bits(field) -> str:
    """SEQUENCE OF 只返回长度头比特，移植自 OTABase get_field_bits()"""
    bits = bytes_to_bit_str(field.to_uper())
    return bits[:_lbs(field)]


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
    """SEQUENCE OF 字段歧义消除，移植自 OTABase find_field_bit_index()"""
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("SEQOF 长度头未在数据包中找到")
    if len(idxs) == 1:
        return idxs.pop()

    fld     = packet.get_at(path)
    old_val = packet.get_val_at(path)
    cur_len = len(old_val)
    new_len = (cur_len + 1 if cur_len < fld._const_sz.ub else cur_len - 1)
    new_val = (old_val * (new_len // len(old_val) + 1))[:new_len]

    packet.set_val_at(path, new_val)
    fld.set_val(new_val)
    nbits = _field_bits(packet.get_at(path))
    npkt  = bytes_to_bit_str(packet.to_uper())
    idxs  = _find_all(npkt, nbits) & idxs

    packet.set_val_at(path, old_val)
    fld.set_val(old_val)
    if not idxs:
        raise ValueError("SEQOF 歧义消除失败")
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]

# ── 变异比特生成 ──────────────────────────────────────────────────────────────

def _seqof_muts(field) -> List[Tuple[str, int]]:
    """
    4 条 SEQUENCE OF 长度头变异，移植自 OTABase mutate_rrc_seqof_field()。
    内容（元素比特）保持不变，仅替换长度头，delta 始终为 0。
    """
    n_elem = len(field.get_val_at([]))
    lbs_   = _lbs(field)
    maxe   = 2**lbs_ - 1

    return [
        (format(0,      f"0{lbs_}b"), 0),
        (format(n_elem, f"0{lbs_}b"), 0),
        (format(random.randint(0, maxe), f"0{lbs_}b"), 0),
        (format(maxe,   f"0{lbs_}b"), 0),
    ]

# ── 公开接口 ──────────────────────────────────────────────────────────────────

def mutate_sequence_of(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> List[Tuple[str, str, List[str]]]:
    """
    对合法 RRC 消息中的 SEQUENCE OF 字段执行比特流级变异。

    参数：
        uper_hex:     合法消息的 UPER 十六进制编码
        message_type: 消息类型名称（用于输出元组）
        target_path:  目标字段路径列表
        seed:         随机数种子（可选，用于复现结果）

    返回：
        [(mutated_uper_hex, message_type, target_path), ...] 列表
    """
    if seed is not None:
        random.seed(seed)

    pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    fld = pkt.get_at(target_path)
    fld.set_val(pkt.get_val_at(target_path))

    if fld.TYPE != "SEQUENCE OF":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 SEQUENCE OF")

    bit_muts = _seqof_muts(fld)

    pkt_bits = bytes_to_bit_str(pkt.to_uper())
    fld_bits = _field_bits(fld)
    fld_idx  = _find_index(pkt_bits, fld_bits, target_path, pkt)

    # 恢复原始数据包
    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for (mut_bits, _delta) in bit_muts:
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path))
    return results
