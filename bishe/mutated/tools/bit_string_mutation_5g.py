"""
5G NR BIT_STRING 字段变异工具

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
    bytes_to_bit_str, bit_str_to_bytes,
    generate_random_bytes,
    encode_unbound_length, generate_invalid_length_encoding,
    n_random_bits,
)

MAX_OTA      = 2048
OVERFLOW_LEN = 100


def _field_bits(field) -> str:
    """BIT STRING 字段比特串（去除填充）"""
    bits = bytes_to_bit_str(field.to_uper())
    if field._const_sz is not None:
        max_len  = field._const_sz.ub - field._const_sz.lb
        lbs      = math.floor(math.log2(max_len)) + 1
        cont_len = int(bits[:lbs], 2) + field._const_sz.lb
        bits     = bits[:(cont_len + lbs)]
    return bits


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
    """在数据包比特流中定位 BIT STRING 字段位置"""
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("字段未在数据包比特流中找到")
    if len(idxs) == 1:
        return idxs.pop()

    fld         = packet.get_at(path)
    oval, olen  = packet.get_val_at(path)
    nval = oval
    while nval == oval:
        nval = random.randint(0, 2**olen - 1)
    packet.set_val_at(path, (nval, olen))
    fld.set_val((nval, olen))
    nbits = _field_bits(packet.get_at(path))
    npkt  = bytes_to_bit_str(packet.to_uper())
    idxs  = _find_all(npkt, nbits) & idxs
    packet.set_val_at(path, (oval, olen))
    fld.set_val((oval, olen))
    if not idxs:
        raise ValueError("BIT STRING 歧义消除失败")
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]


def _constrained_bit_muts(field) -> List[Tuple[str, int]]:
    """受约束 BIT STRING 4 条变异"""
    fld_bits = _field_bits(field)
    maxl     = field._const_sz.ub - field._const_sz.lb
    lbs      = math.floor(math.log2(maxl)) + 1
    maxe     = 2**lbs - 1

    def gen(lval: int, clen: int):
        bits  = format(lval, f"0{lbs}b") + n_random_bits(clen)
        delta = len(bits) - len(fld_bits)
        return (bits, delta)

    r = random.randint(0, max(0, maxl - 1))
    return [
        gen(r, 0),
        gen(0, OVERFLOW_LEN + field._const_sz.lb),
        gen(random.randint(0, max(0, maxl - 1)),
            random.randint(0, max(0, maxl - 1)) + field._const_sz.lb + 1),
        gen(maxe, maxe + OVERFLOW_LEN),
    ]


def _unconstrained_bit_muts(field) -> List[Tuple[str, int]]:
    """无约束 BIT STRING 变异"""
    fld_bits = _field_bits(field)
    muts     = []

    def gen(enc: list, clen: int):
        lbytes = enc[0]
        bits   = bytes_to_bit_str(lbytes) + n_random_bits(clen)
        delta  = len(bits) - len(fld_bits)
        return (bits, delta)

    for l in [0, 127, 128]:
        enc  = encode_unbound_length(l)
        safe = max(1, min(MAX_OTA, l - 1 if l > 0 else 1))
        muts.append(gen(enc, 0))
        muts.append(gen(enc, random.randint(1, safe)))
        muts.append(gen(enc, min(MAX_OTA, l + OVERFLOW_LEN)))

    inv   = [generate_invalid_length_encoding()]
    inv_l = int.from_bytes(inv[0], "big")
    muts.append(gen(inv, 0))
    muts.append(gen(inv, random.randint(1, min(MAX_OTA, max(1, inv_l - 1)))))
    muts.append(gen(inv, min(MAX_OTA, inv_l + OVERFLOW_LEN)))
    return muts


def mutate_bit_string_5g(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> List[Tuple[str, str, List[str]]]:
    """
    对 5G NR RRC 消息中的 BIT STRING 字段执行比特流级变异。

    参数：
        uper_hex:     合法消息的 UPER 十六进制编码
        message_type: 消息类型名称
        target_path:  目标字段路径列表
        seed:         随机数种子（可选）

    返回：
        [(mutated_uper_hex, message_type, target_path), ...] 列表
    """
    if seed is not None:
        random.seed(seed)

    pkt = RRCNR.NR_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    fld = pkt.get_at(target_path)
    fld.set_val(pkt.get_val_at(target_path))

    if fld.TYPE != "BIT STRING":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 BIT STRING")

    bit_muts = (_constrained_bit_muts(fld)
                if fld._const_sz is not None
                else _unconstrained_bit_muts(fld))

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
