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
    normalize_field_path_for_pycrate,
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


def _mutate_through_containing_5g(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int],
    max_strategies: Optional[int],
) -> List[Tuple[str, str, List[str], int]]:
    """
    处理路径含 '*'（CONTAINING 嵌入字段）的 OCTET STRING 变异。

    问题根因：pycrate 类型对象是全局单例。当外层消息（如 rrcResume）自身也有
    同名字段（如 masterCellGroup）时，pkt.to_uper() 在编码外层字段时会覆盖
    全局 _val，导致内层 CONTAINING 结构里的同名字段被错误编码，使 fld_bits
    无法在 pkt_bits 中找到。

    修复策略：完全在内层 schema 的独立上下文中完成「定位 + 变异」，
    仅在最后重建外层报文时才回到外层（使用原始字节而非 pycrate 重编码来
    保留外层其他字段的编码）。
    """
    star_idx      = target_path.index('*')
    outer_raw     = target_path[:star_idx]
    inner_raw     = target_path[star_idx + 1:]

    outer_val_path  = normalize_field_path_for_get_val_at(outer_raw)
    outer_norm_path = normalize_field_path_for_pycrate(outer_raw)

    # inner_raw[0] 是 CONTAINING 的类型名（如 'RRCReconfiguration'），不是字段名。
    # inner_schema 已经 IS 该类型，直接从它的第一个字段名开始导航。
    inner_raw_fields = inner_raw[1:] if inner_raw else inner_raw
    inner_val_path   = normalize_field_path_for_get_val_at(inner_raw_fields)

    pkt = RRCNR.NR_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    # ── Step 1: 在 from_uper 之后、pkt.to_uper() 之前立刻提取内层字节 ────────
    # pycrate 全局状态此时：内层 masterCellGroup（解码顺序最后）的 _val 是正确值。
    # 调用 outer_fld._const_cont.to_uper() 可在状态被外层 to_uper() 污染之前
    # 得到正确的内层 RRCReconfiguration 编码字节。
    outer_fld   = get_field_type_at_value_path(pkt, outer_val_path)
    inner_schema = outer_fld._const_cont
    if inner_schema is None:
        raise ValueError("CONTAINING 字段没有 _const_cont，无法提取内层 schema")
    inner_bytes = inner_schema.to_uper()  # 内层正确编码（全局状态未被污染）

    # ── Step 2: 完全在内层 schema 上下文中工作 ────────────────────────────────
    inner_schema.from_uper(inner_bytes)

    inner_fld     = get_field_type_at_value_path(inner_schema, inner_val_path)
    inner_old_val = inner_schema.get_val_at(inner_val_path)

    if inner_fld.TYPE != "OCTET STRING":
        raise TypeError(f"字段类型为 {inner_fld.TYPE}，不是 OCTET STRING")

    inner_fld._val = inner_old_val

    if inner_fld._const_sz is not None:
        bit_muts = _constrained_octet_muts(inner_fld)
        strategy_indices = list(range(1, len(bit_muts) + 1))
    else:
        bit_muts = _unconstrained_octet_muts(inner_fld)
        if max_strategies is not None and max_strategies < len(bit_muts):
            sampled = sorted(random.sample(range(len(bit_muts)), max_strategies))
            bit_muts = [bit_muts[i] for i in sampled]
            strategy_indices = [i + 1 for i in sampled]
        else:
            strategy_indices = list(range(1, len(bit_muts) + 1))

    # inner_schema 中没有外层同名字段，to_uper() 不会覆盖内层 _val
    inner_pkt_bits = bytes_to_bit_str(inner_schema.to_uper())
    inner_fld._val = inner_old_val          # 防御性恢复（to_uper 可能修改 _val）
    inner_fld_bits = _field_bits(inner_fld)

    inner_schema.from_uper(inner_bytes)
    inner_fld_idx = _find_index(
        inner_pkt_bits, inner_fld_bits, inner_val_path,
        inner_schema, inner_fld, inner_old_val,
    )

    inner_schema.from_uper(inner_bytes)
    inner_pkt_bits = bytes_to_bit_str(inner_schema.to_uper())

    # ── Step 3: 逐条生成变异，重建外层报文 ────────────────────────────────────
    # 外层重建策略：不依赖 pkt.to_uper()（会污染全局 _val），而是在原始外层
    # 比特流中直接把 CONTAINING OCTET STRING 的字节内容替换为变异后的内层字节。
    #
    # 具体做法：
    #   a) 用原始 uper_hex 得到外层比特流（不经过 pycrate 重编码）
    #   b) 找到 CONTAINING OCTET STRING（nr-SCG-r16）在原始比特流中的位置
    #      —— 方法：设置 outer_fld._val = inner_bytes（正确内层编码字节），
    #         则 outer_fld.to_uper() = [length_det][inner_bytes]，
    #         这段比特串应出现在原始比特流中（因为原始报文的内层编码
    #         可能与 inner_schema.to_uper() 不同，所以先尝试在 pycrate
    #         重编码的外层比特流中查找，如找不到则回退到原始比特流）
    #   c) 将找到的 CONTAINING 字段替换为包含变异内层字节的新编码
    pkt.from_uper(bytes.fromhex(uper_hex))
    outer_fld_fresh = get_field_type_at_value_path(pkt, outer_val_path)

    # 用 inner_bytes（内层正确编码）构造外层 OCTET STRING 的比特表示
    outer_fld_fresh._val = inner_bytes
    outer_containing_bits = _field_bits(outer_fld_fresh)

    # 先在 pycrate 重编码的外层比特流中查找（重编码时外层已被设为 inner_bytes）
    outer_pkt_bits = bytes_to_bit_str(pkt.to_uper())
    outer_positions = _find_all(outer_pkt_bits, outer_containing_bits)
    if not outer_positions:
        # 回退：在原始比特流中查找
        outer_pkt_bits   = bytes_to_bit_str(bytes.fromhex(uper_hex))
        outer_positions  = _find_all(outer_pkt_bits, outer_containing_bits)
    if not outer_positions:
        raise ValueError(
            "CONTAINING OCTET STRING（外层包裹字段）在报文比特流中未找到，"
            "无法定位以完成外层重建"
        )
    outer_fld_start = min(outer_positions)

    results = []
    for strategy_idx, (mut_bits, _delta) in zip(strategy_indices, bit_muts):
        # 在内层比特流中替换目标字段
        mutated_inner_bits  = _replace(inner_pkt_bits, inner_fld_bits, inner_fld_idx, mut_bits)
        mutated_inner_bytes = bit_str_to_bytes(mutated_inner_bits)

        # 构造含变异内层字节的外层 OCTET STRING 编码
        outer_fld_fresh._val = mutated_inner_bytes
        new_outer_fld_bits   = bytes_to_bit_str(outer_fld_fresh.to_uper())

        # 替换外层报文中的 CONTAINING 字段
        mutated_outer_bits = _replace(
            outer_pkt_bits, outer_containing_bits, outer_fld_start, new_outer_fld_bits
        )
        results.append((bit_str_to_bytes(mutated_outer_bits).hex(),
                        message_type, target_path, strategy_idx))

    return results


def mutate_octet_string_5g(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
    max_strategies: Optional[int] = None,
) -> List[Tuple[str, str, List[str], int]]:
    """
    对 5G NR RRC 消息中的 OCTET STRING 字段执行比特流级变异。

    参数：
        uper_hex:        合法消息的 UPER 十六进制编码字符串
        message_type:    消息类型名称
        target_path:     目标字段路径列表
        seed:            随机数种子（可选）
        max_strategies:  无约束字段时，从全部策略中随机挑选的最大数量（None 表示全部使用）

    返回：
        [(mutated_uper_hex, message_type, target_path, strategy_idx), ...] 列表
        strategy_idx 为原始 1-based 编号（从全部策略中采样时保留原始编号）
    """
    if seed is not None:
        random.seed(seed)

    # 路径含 '*' 表示目标字段在 CONTAINING OCTET STRING 内部，用专门逻辑处理
    if '*' in target_path:
        return _mutate_through_containing_5g(
            uper_hex, message_type, target_path, seed, max_strategies
        )

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
        strategy_indices = list(range(1, len(bit_muts) + 1))
    else:
        bit_muts = _unconstrained_octet_muts(fld)
        if max_strategies is not None and max_strategies < len(bit_muts):
            sampled = sorted(random.sample(range(len(bit_muts)), max_strategies))
            bit_muts = [bit_muts[i] for i in sampled]
            strategy_indices = [i + 1 for i in sampled]
        else:
            strategy_indices = list(range(1, len(bit_muts) + 1))

    pkt_bits  = bytes_to_bit_str(pkt.to_uper())
    fld_bits  = _field_bits(fld)

    pkt.from_uper(bytes.fromhex(uper_hex))
    fld_idx   = _find_index(pkt_bits, fld_bits, val_path, pkt, fld, old_val)

    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for strategy_idx, (mut_bits, _delta) in zip(strategy_indices, bit_muts):
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path, strategy_idx))

    return results
