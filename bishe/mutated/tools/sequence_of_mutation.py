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
    bytes_to_bit_str,
    bit_str_to_bytes,
    normalize_field_path_for_pycrate,
)

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _lbs(field) -> int:
    """计算 SEQUENCE OF 长度头所需的比特数（同 OTABase）；SIZE 固定（ub==lb）时长度为 0 无法变异。"""
    max_len = field._const_sz.ub - field._const_sz.lb
    if max_len <= 0:
        return 0
    return math.floor(math.log2(max_len)) + 1


def _field_bits(field) -> str:
    """SEQUENCE OF 只返回长度头比特，移植自 OTABase get_field_bits()；长度 0 时返回空串。"""
    lbs = _lbs(field)
    if lbs <= 0:
        return ""
    bits = bytes_to_bit_str(field.to_uper())
    return bits[:lbs]


def _find_all(pkt_bits: str, tgt: str) -> set:
    s, idxs = 0, set()
    while True:
        i = pkt_bits.find(tgt, s)
        if i == -1:
            break
        idxs.add(i)
        s = i + 1
    return idxs


def _find_index(pkt_bits: str, fld_bits: str, norm_path: list, packet) -> int:
    """
    SEQUENCE OF 字段歧义消除（对齐 artifact rrc_utils find_field_bit_index）。
    统一用 norm_path：get_at / get_val_at / set_val_at 均用容器路径，取到的是整个 list，
    避免对单个元素 set_val 导致 schema 校验失败（如 SI-OrPSI-GERAN.si invalid value）。
    """
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("SEQOF 长度头未在数据包中找到")
    if len(idxs) == 1:
        return idxs.pop()

    original_idxs = set(idxs)
    fld = packet.get_at(norm_path)
    old_val = packet.get_val_at(norm_path)
    cur_len = len(old_val)
    new_len = (cur_len + 1 if cur_len < fld._const_sz.ub else cur_len - 1)
    new_val = (list(old_val) * (new_len // len(old_val) + 1))[:new_len]

    packet.set_val_at(norm_path, new_val)
    fld._val = new_val
    nbits = _field_bits(fld)
    npkt = bytes_to_bit_str(packet.to_uper())
    idxs = _find_all(npkt, nbits) & original_idxs

    if not idxs:
        return min(original_idxs)
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]


def _container_path(pkt, norm_path: list) -> list:
    """
    返回 SEQUENCE OF 容器的路径：get_val_at(path) 在 list 上只能用整数下标，
    故 path 必须止于 listName。从 norm_path 向前截断，找到最大的 k 使得
    get_at(norm_path[:k]) 为 SEQUENCE OF 且 get_val_at(norm_path[:k]) 为 list（可接受）。
    """
    from pycrate.pycrate_asn1rt.err import ASN1Err
    for k in range(len(norm_path) - 1, 0, -1):
        try:
            path_k = norm_path[:k]
            parent = pkt.get_at(path_k)
            if getattr(parent, "TYPE", None) != "SEQUENCE OF":
                continue
            val = pkt.get_val_at(path_k)
            if isinstance(val, list):
                return path_k
        except (ASN1Err, KeyError, TypeError):
            continue
    # 退化为整段 norm_path（仅当 norm_path 本身即为容器路径时有效）
    return norm_path

# ── 变异比特生成 ──────────────────────────────────────────────────────────────

def _seqof_muts(field) -> List[Tuple[str, int]]:
    """
    4 条 SEQUENCE OF 长度头变异，移植自 OTABase mutate_rrc_seqof_field()。
    SIZE 固定（ub==lb）时无长度头可变异，返回空列表。
    """
    lbs_ = _lbs(field)
    if lbs_ <= 0:
        return []
    n_elem = len(field.get_val_at([]))
    maxe = 2**lbs_ - 1
    return [
        (format(0, f"0{lbs_}b"), 0),
        (format(n_elem, f"0{lbs_}b"), 0),
        (format(random.randint(0, maxe), f"0{lbs_}b"), 0),
        (format(maxe, f"0{lbs_}b"), 0),
    ]

# ── 公开接口 ──────────────────────────────────────────────────────────────────

def mutate_sequence_of(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> List[Tuple[str, str, List[str], int]]:
    """
    对合法 RRC 消息中的 SEQUENCE OF 字段执行比特流级变异。

    参数：
        uper_hex:     合法消息的 UPER 十六进制编码
        message_type: 消息类型名称（用于输出元组）
        target_path:  目标字段路径列表
        seed:         随机数种子（可选，用于复现结果）

    返回：
        [(mutated_uper_hex, message_type, target_path, strategy_idx), ...] 列表
    """
    if seed is not None:
        random.seed(seed)

    pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    # 与 artifact 一致：SEQUENCE OF 变异针对容器；路径可能指向容器或容器内字段，统一用容器路径做 get_val_at/set_val_at
    norm_path = normalize_field_path_for_pycrate(target_path)
    container_path = _container_path(pkt, norm_path)
    fld = pkt.get_at(container_path)

    if fld.TYPE != "SEQUENCE OF":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 SEQUENCE OF")

    # 用容器路径取整段 SEQUENCE OF 的值（list），避免对元素 set_val 触发 schema 校验
    container_val = pkt.get_val_at(container_path)
    if fld.get_val() != container_val:
        fld._val = container_val

    bit_muts = _seqof_muts(fld)
    if not bit_muts:
        # SIZE 固定（ub==lb）时无长度头可变异，与 artifact 一致跳过
        return []

    pkt_bits = bytes_to_bit_str(pkt.to_uper())
    fld_bits = _field_bits(fld)
    if not fld_bits:
        return []

    # to_uper() 可能修改 pycrate 内部状态，需重新加载确保 _find_index 中 set_val_at 可用
    pkt.from_uper(bytes.fromhex(uper_hex))
    fld_idx = _find_index(pkt_bits, fld_bits, container_path, pkt)

    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for strategy_idx, (mut_bits, _delta) in enumerate(bit_muts, 1):
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path, strategy_idx))
    return results
