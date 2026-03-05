"""
OCTET_STRING 字段变异工具

接口：
  输入  uper_hex, message_type, target_path
  输出  变异后的 (uper_hex, message_type, target_path) 列表

完全移植自 OTABase rrc_fuzzer.py::mutate_rrc_octet_field()
核心：直接在 UPER 比特流层面替换字段，绕过 pycrate 约束校验。
"""
import math
import random
from typing import List, Tuple, Optional

from pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT  = True

from pycrate_asn1dir import RRCLTE

from .mutation_utils import (
    bytes_to_bit_str, bit_str_to_bytes,
    generate_random_bytes,
    encode_unbound_length, generate_invalid_length_encoding,
    n_random_bits,
)

MAX_OTA      = 2048
OVERFLOW_LEN = 100

# ── 共享比特工具 ──────────────────────────────────────────────────────────────

def _field_bits(field) -> str:
    """返回字段的 UPER 比特串（去除字节对齐填充位）。"""
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


def _find_index(pkt_bits: str, fld_bits: str, path: list, packet) -> int:
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("字段未在数据包比特流中找到")
    if len(idxs) == 1:
        return idxs.pop()
    # 歧义消除：改变字段值，求新旧位置交集
    fld = packet.get_at(path)
    old = packet.get_val_at(path)
    new = old
    while new == old:
        new = random.randbytes(len(old))
    packet.set_val_at(path, new)
    fld.set_val(new)
    new_bits = _field_bits(packet.get_at(path))
    new_pkt  = bytes_to_bit_str(packet.to_uper())
    idxs     = _find_all(new_pkt, new_bits) & idxs
    packet.set_val_at(path, old)
    fld.set_val(old)
    if not idxs:
        raise ValueError("OCTET STRING 歧义消除失败")
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]

# ── 变异比特生成 ──────────────────────────────────────────────────────────────

def _constrained_octet_muts(field) -> List[Tuple[str, int]]:
    """
    受约束 OCTET STRING 变异（字段有 SIZE(lb..ub) 约束），共 4 条。
    移植自 OTABase mutate_rrc_octet_field()。

    UPER 编码格式：[长度头: lbs 位][内容字节]
      - lbs = floor(log2(ub - lb)) + 1，即表示最大范围所需的最少比特数
      - 最大可编码长度值 maxe = 2^lbs - 1（可能超出 ub，故为非法）
    """
    fb    = field.to_uper()          # 字段原始 UPER 编码字节
    fval  = field.get_val_at([])     # 字段原始值（bytes）
    fsz   = len(fb)                  # 字段原始字节数
    maxl  = field._const_sz.ub - field._const_sz.lb   # 合法最大长度
    lbs   = math.floor(math.log2(maxl)) + 1           # 长度头比特数
    maxe  = 2**lbs - 1               # 长度头能表示的最大值（可能非法）

    def gen(length: int, clen: int):
        """构造变异字段比特串：[length 编码为 lbs 位] + [clen 字节内容]"""
        content = (fval + generate_random_bytes(clen - len(fval))
                   if clen > len(fval) else fb[:clen])
        bits  = format(length, f"0{lbs}b") + bytes_to_bit_str(content)
        delta = len(bit_str_to_bytes(bits)) - fsz
        return (bits, delta * 8)

    r = random.randint(0, max(0, maxl - 1))
    return [
        # 变异 1：合法随机长度 r，但内容为空（长度声明 > 实际内容，截断）
        gen(r, 0),
        # 变异 2：长度声明为 0，但填入 OVERFLOW_LEN(100) 字节内容（长度为 0 但有大量内容）
        gen(0, OVERFLOW_LEN),
        # 变异 3：随机合法长度，但内容比声明多 1 字节（内容越界）
        gen(random.randint(0, max(0, maxl - 1)),
            random.randint(0, max(0, maxl - 1)) + field._const_sz.lb + 1),
        # 变异 4：长度头设为最大可编码值 maxe（≥ ub，超出约束上界），内容填满 ub 字节
        gen(maxe, field._const_sz.ub),
    ]


def _unconstrained_octet_muts(field) -> List[Tuple[str, int]]:
    """
    无约束 OCTET STRING 变异（字段无 SIZE 约束），共 22 条。
    移植自 OTABase mutate_rrc_octet_field()。

    无约束 OCTET STRING 的 UPER 长度编码使用变长格式（encode_unbound_length）：
      - 0~127       : 1 字节，首位为 0，如 0x00~0x7F
      - 128~16383   : 2 字节，首两位为 10，如 0x8080~0xBFFF
      - ≥16384      : 分片编码，首字节 0xC1/0xC2/0xC3 表示 n×16384 字节分片
    """
    fb   = field.to_uper()       # 字段原始 UPER 编码字节
    fval = field.get_val_at([])  # 字段原始值（bytes）
    fsz  = len(fb)               # 字段原始字节数
    muts = []

    def gen(enc: list, clen: int):
        """构造变异字段：[enc[0]（长度编码字节)] + [clen 字节内容]"""
        content       = (fval + generate_random_bytes(clen - len(fval))
                         if clen > len(fval) else fb[:clen])
        mutated_bytes = enc[0] + content
        delta         = len(mutated_bytes) - fsz
        return ("".join(format(b, "08b") for b in mutated_bytes), delta * 8)

    # ── 10 个边界长度值，每个生成 2 条变异（共 20 条） ────────────────────────
    # 边界选取覆盖：单字节上界(127)、双字节切换点(128)、
    # 分片边界(16383/16384)、2×/3× 分片边界、协议最大值(65535)
    for l in [0, 127, 128, 2**14 - 1, 2**14, 2*(2**14),
              2*(2**14) + 1, 3*(2**14), 3*(2**14) + 1, 2**16 - 1]:
        enc  = encode_unbound_length(l)
        safe = max(1, min(MAX_OTA, l - 1 if l > 0 else 1))
        # 子变异 A：声明长度为 l，但内容为空（长度声明 > 实际内容）
        muts.append(gen(enc, 0))
        # 子变异 B：声明长度为 l，内容随机填 1~(l-1) 字节（内容不足声明长度）
        muts.append(gen(enc, random.randint(1, safe)))

    # ── 非法长度编码，生成 2 条变异（共 22 条） ──────────────────────────────
    # generate_invalid_length_encoding() 生成不符合 ASN.1 规范的长度字节序列
    inv   = [generate_invalid_length_encoding()]
    inv_l = int.from_bytes(inv[0], "big")
    # 变异 21：非法长度编码 + 空内容
    muts.append(gen(inv, 0))
    # 变异 22：非法长度编码 + 比声明长度少 1 字节的内容
    muts.append(gen(inv, random.randint(1, min(MAX_OTA, max(1, inv_l - 1)))))
    return muts

# ── 公开接口 ──────────────────────────────────────────────────────────────────

def mutate_octet_string(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> List[Tuple[str, str, List[str]]]:
    """
    对合法 RRC 消息中的 OCTET STRING 字段执行比特流级变异。

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

    if fld.TYPE != "OCTET STRING":
        raise TypeError(f"字段类型为 {fld.TYPE}，不是 OCTET STRING")

    bit_muts = (_constrained_octet_muts(fld)
                if fld._const_sz is not None
                else _unconstrained_octet_muts(fld))

    pkt_bits  = bytes_to_bit_str(pkt.to_uper())
    fld_bits  = _field_bits(fld)
    fld_idx   = _find_index(pkt_bits, fld_bits, target_path, pkt)

    # 恢复原始数据包（_find_index 的歧义消除可能修改了 pkt）
    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for (mut_bits, _delta) in bit_muts:
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path))
    return results
