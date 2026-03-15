"""
5G NR OCTET_STRING 字段变异工具

接口与 4G 版本完全一致，仅协议定义替换为 NR RRC。
"""

import math
import random
from typing import List, Tuple, Optional

from pycrate.pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT  = True

from bishe.pycrate_asn1obj.nr_5g import RRCNR

from .mutation_utils import (
    bytes_to_bit_str,
    bit_str_to_bytes,
    generate_random_bytes,
    encode_unbound_length,
    generate_invalid_length_encoding,
    n_random_bits,
    normalize_field_path_for_get_val_at,
    get_field_type_at_value_path,
)

MAX_OTA      = 2048
OVERFLOW_LEN = 100


def _field_bits(field) -> str:
    """提取字段的有效 UPER 比特串（去除填充）"""
    bits = bytes_to_bit_str(field.to_uper())
    if field._const_sz is not None:
        max_len = field._const_sz.ub - field._const_sz.lb
        lbs     = math.floor(math.log2(max_len)) + 1
        if lbs % 8 != 0:
            bits = bits[:-(8 - lbs % 8)]
    return bits


def _find_all(pkt_bits: str, tgt: str) -> set:
    s, idx_set = 0, set()
    while True:
        i = pkt_bits.find(tgt, s)
        if i == -1:
            break
        idx_set.add(i)
        s = i + 1
    return idx_set


def _find_index(pkt_bits: str, fld_bits: str, val_path: list, packet, fld, old_val) -> int:
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("字段未在数据包比特流中找到")
    if len(idxs) == 1:
        return idxs.pop()

    original_idxs = set(idxs)

    if not isinstance(old_val, (bytes, bytearray)):
        return min(original_idxs)

    new = old_val
    while new == old_val:
        new = random.randbytes(len(old_val))
    packet.set_val_at(val_path, new)
    fld._val = new
    new_bits = _field_bits(fld)
    new_pkt  = bytes_to_bit_str(packet.to_uper())
    idxs     = _find_all(new_pkt, new_bits) & original_idxs

    if not idxs:
        return min(original_idxs)
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]


def _constrained_octet_muts(field) -> List[Tuple[str, int]]:
    """受约束 OCTET STRING 变异（4 条）"""
    fb    = field.to_uper()
    fval  = field.get_val_at([])
    if not isinstance(fval, (bytes, bytearray)):
        fval = fb  # CONTAINING 类型：用 UPER 编码作为内容素材
    fsz   = len(fb)
    maxl  = field._const_sz.ub - field._const_sz.lb
    lbs   = math.floor(math.log2(maxl)) + 1
    maxe  = 2**lbs - 1

    def gen(length: int, clen: int):
        content = (fval + generate_random_bytes(clen - len(fval))
                   if clen > len(fval) else fval[:clen])
        bits  = format(length, f"0{lbs}b") + bytes_to_bit_str(content)
        delta = len(bit_str_to_bytes(bits)) - fsz
        return (bits, delta * 8)

    r = random.randint(0, max(0, maxl - 1))

    return [
        gen(r, 0),
        gen(0, OVERFLOW_LEN),
        gen(random.randint(0, max(0, maxl - 1)),
            random.randint(0, max(0, maxl - 1)) + field._const_sz.lb + 1),
        gen(maxe, field._const_sz.ub),
    ]


def _unconstrained_octet_muts(field) -> List[Tuple[str, int]]:
    """无约束 OCTET STRING 变异（22 条）"""
    fb   = field.to_uper()
    fval = field.get_val_at([])
    if not isinstance(fval, (bytes, bytearray)):
        fval = fb  # CONTAINING 类型：用 UPER 编码作为内容素材
    fsz  = len(fb)
    muts = []

    def gen(enc: list, clen: int):
        content       = (fval + generate_random_bytes(clen - len(fval))
                         if clen > len(fval) else fval[:clen])
        mutated_bytes = enc[0] + content
        delta         = len(mutated_bytes) - fsz
        return ("".join(format(b, "08b") for b in mutated_bytes), delta * 8)

    for l in [0, 127, 128, 2**14 - 1, 2**14, 2*(2**14),
              2*(2**14) + 1, 3*(2**14), 3*(2**14) + 1, 2**16 - 1]:
        enc  = encode_unbound_length(l)
        safe = max(1, min(MAX_OTA, l - 1 if l > 0 else 1))
        muts.append(gen(enc, 0))
        muts.append(gen(enc, random.randint(1, safe)))

    inv   = [generate_invalid_length_encoding()]
    inv_l = int.from_bytes(inv[0], "big")
    muts.append(gen(inv, 0))
    muts.append(gen(inv, random.randint(1, min(MAX_OTA, max(1, inv_l - 1)))))

    return muts


def mutate_octet_string_5g(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
    max_strategies: Optional[int] = None,
) -> List[Tuple[str, str, List[str]]]:
    """
    对 5G NR RRC 消息中的 OCTET STRING 字段执行比特流级变异。

    参数：
        uper_hex:        合法消息的 UPER 十六进制编码字符串
        message_type:    消息类型名称
        target_path:     目标字段路径列表
        seed:            随机数种子（可选）
        max_strategies:  无约束字段时，从全部策略中随机挑选的最大数量（None 表示全部使用）

    返回：
        [(mutated_uper_hex, message_type, target_path), ...] 列表
    """
    if seed is not None:
        random.seed(seed)

    pkt = RRCNR.NR_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    val_path = normalize_field_path_for_get_val_at(target_path)

    fld = get_field_type_at_value_path(pkt, val_path)
    old_val = pkt.get_val_at(val_path)
    fld._val = old_val

    if fld.TYPE != "OCTET STRING":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 OCTET STRING")

    if fld._const_sz is not None:
        bit_muts = _constrained_octet_muts(fld)
    else:
        bit_muts = _unconstrained_octet_muts(fld)
        if max_strategies is not None and max_strategies < len(bit_muts):
            bit_muts = random.sample(bit_muts, max_strategies)

    pkt_bits  = bytes_to_bit_str(pkt.to_uper())
    fld_bits  = _field_bits(fld)

    pkt.from_uper(bytes.fromhex(uper_hex))
    fld_idx   = _find_index(pkt_bits, fld_bits, val_path, pkt, fld, old_val)

    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for (mut_bits, _delta) in bit_muts:
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path))

    return results
