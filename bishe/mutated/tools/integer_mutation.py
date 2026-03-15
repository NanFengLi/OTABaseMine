"""
INTEGER 字段变异工具

接口:
  输入  uper_hex, message_type, target_path
  输出  变异后的 (uper_hex, message_type, target_path) 列表

移植自 OTABase rrc_fuzzer.py::mutate_rrc_integer_field()
核心:直接在 UPER 比特流层面替换字段,绕过 pycrate 约束校验。

INTEGER 的 UPER 编码格式(受约束,SIZE(lb..ub)):
  编码值 = value - lb,占 lbs = floor(log2(ub - lb)) + 1 位
  因此 lbs 位最多能表示 2^lbs - 1,对应真实值 lb + 2^lbs - 1,
  而规范上界仅为 ub,故 lb + 2^lbs - 1 >= ub,存在可利用的冗余位空间。
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
    normalize_field_path_for_get_val_at,
    get_field_type_at_value_path,
)

# ── 比特工具 ──────────────────────────────────────────────────────────────────

def _lbs(field) -> int:
    """计算 INTEGER 字段的长度头比特数:floor(log2(ub - lb)) + 1"""
    lb = field._const_val.lb
    ub = field._const_val.ub
    return math.floor(math.log2(ub - lb)) + 1


def _field_bits(field) -> str:
    """
    返回 INTEGER 字段在 UPER 中的比特串。
    INTEGER 编码为 (value - lb) 的定长二进制,共 lbs 位,无填充。
    """
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


def _find_index(pkt_bits: str, fld_bits: str, val_path: list, packet, fld, old_val) -> int:
    """
    在数据包比特流中定位 INTEGER 字段位置。
    old_val 由调用方在 to_uper() 之前通过 get_val_at 获取并传入，
    避免 to_uper() 修改 pycrate 内部状态后 get_val_at 失败。
    """
    idxs = _find_all(pkt_bits, fld_bits)
    if not idxs:
        raise ValueError("INTEGER 字段未在数据包比特流中找到")
    if len(idxs) == 1:
        return idxs.pop()
    original_idxs = set(idxs)
    lb      = fld._const_val.lb
    ub      = fld._const_val.ub
    new_val = old_val
    while new_val == old_val:
        new_val = random.randint(lb, ub)
    packet.set_val_at(val_path, new_val)
    fld._val = new_val
    nbits = _field_bits(fld)
    npkt  = bytes_to_bit_str(packet.to_uper())
    idxs  = _find_all(npkt, nbits) & original_idxs
    if not idxs:
        return min(original_idxs)
    return min(idxs)


def _replace(pkt_bits: str, fld_bits: str, idx: int, mut: str) -> str:
    return pkt_bits[:idx] + mut + pkt_bits[idx + len(fld_bits):]

# ── 变异比特生成 ──────────────────────────────────────────────────────────────

def _integer_muts(field) -> List[Tuple[str, int]]:
    """
    INTEGER 3 条变异,移植自 OTABase mutate_rrc_integer_field()。

    设 lbs = floor(log2(ub - lb)) + 1(字段实际占用比特数):

      变异 1:范围内随机合法值
        编码 = randint(lb, ub) - lb,在 [0, ub-lb] 内,合法但随机
      变异 2:比特位最大可表示值(利用冗余比特空间)
        编码 = 2^lbs - 1,对应真实值 lb + 2^lbs - 1 >= ub(超出规范上界)
      变异 3:上界溢出值(ub + 1)
        编码 = ub - lb + 1,比最大合法编码值大 1(边界溢出)
    """
    lb      = field._const_val.lb
    ub      = field._const_val.ub
    lbs_    = _lbs(field)
    cur_bits = _field_bits(field)

    # 变异 1:范围内随机合法值(编码合规,但值随机)
    rand_val    = random.randint(lb, ub)
    rand_bits   = format(rand_val - lb, f"0{lbs_}b")

    # 变异 2:比特位可表示的最大值(编码冗余空间溢出)
    max_repr    = 2**lbs_ - 1                    # 最大编码值(对应真实值 lb + 2^lbs - 1)
    maxrepr_bits = format(max_repr, f"0{lbs_}b")

    # 变异 3:上界 +1 溢出(仅超出规范上界 1 个单位)
    overflow    = ub - lb + 1                    # 编码值 = ub - lb + 1
    overflow_bits = format(overflow, f"0{lbs_}b")

    delta = 0  # INTEGER 定长编码,替换后数据包长度不变
    return [
        (rand_bits,     delta),
        (maxrepr_bits,  delta),
        (overflow_bits, delta),
    ]

# ── 公开接口 ──────────────────────────────────────────────────────────────────

def mutate_integer(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> List[Tuple[str, str, List[str]]]:
    """
    对合法 RRC 消息中的 INTEGER 字段执行比特流级变异。

    参数:
        uper_hex:     合法消息的 UPER 十六进制编码
        message_type: 消息类型名称(用于输出元组)
        target_path:  目标字段路径列表
        seed:         随机数种子(可选,用于复现结果)

    返回:
        [(mutated_uper_hex, message_type, target_path), ...] 列表,共 3 条
    """
    if seed is not None:
        random.seed(seed)

    pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    val_path = normalize_field_path_for_get_val_at(target_path)

    fld = get_field_type_at_value_path(pkt, val_path)
    old_val = pkt.get_val_at(val_path)
    fld._val = old_val

    if fld.TYPE != "INTEGER":
        raise TypeError(f"字段类型为 {fld.TYPE},不是 INTEGER")

    bit_muts = _integer_muts(fld)

    pkt_bits = bytes_to_bit_str(pkt.to_uper())
    fld_bits = _field_bits(fld)

    # to_uper() 可能修改 pycrate 内部状态（如移除 DEFAULT 值），需重新加载确保 set_val_at 可用
    pkt.from_uper(bytes.fromhex(uper_hex))
    fld_idx  = _find_index(pkt_bits, fld_bits, val_path, pkt, fld, old_val)

    pkt.from_uper(bytes.fromhex(uper_hex))
    pkt_bits = bytes_to_bit_str(pkt.to_uper())

    results = []
    for (mut_bits, _delta) in bit_muts:
        mutated = bit_str_to_bytes(_replace(pkt_bits, fld_bits, fld_idx, mut_bits))
        results.append((mutated.hex(), message_type, target_path))
    return results
