"""
变异工具函数

基于 OTABase 模糊测试策略的 RRC 消息变异辅助函数。
"""

import math
import random
import secrets
from typing import List, Tuple, Dict, Any, Optional


def bytes_to_bit_str(data: bytes) -> str:
    """
    将字节转换为比特串。
    
    参数：
        data: 要转换的字节
        
    返回：
        由 '0' 和 '1' 组成的字符串
    """
    return ''.join(format(byte, '08b') for byte in data)


def bit_str_to_bytes(bit_str: str) -> bytes:
    """
    将比特串转换为字节。
    
    参数：
        bit_str: 由 '0' 和 '1' 组成的字符串
        
    返回：
        字节表示
    """
    # 补齐至 8 的倍数
    padding = (8 - len(bit_str) % 8) % 8
    bit_str += '0' * padding
    return bytes(int(bit_str[i:i+8], 2) for i in range(0, len(bit_str), 8))


def n_random_bits(n: int) -> str:
    """
    生成长度为 n 的随机比特串。
    
    参数：
        n: 比特串长度
        
    返回：
        随机比特串
    """
    if n == 0:
        return ''
    return format(secrets.randbits(n), f'0{n}b')


def generate_random_bytes(n: int) -> bytes:
    """
    生成 n 个随机字节。
    
    参数：
        n: 要生成的字节数
        
    返回：
        随机字节
    """
    return bytes(random.getrandbits(8) for _ in range(n))


def encode_unbound_length(length: int) -> List[bytes]:
    """
    按照 PER 编码规则进行无界长度编码。
    
    共 3 种情况：
    1. 长度属于 (0, 127)，用 1 字节编码
    2. 长度属于 (128, 16383)，用 2 字节编码，第 0 字节第 8 位为 1、第 7 位为 0
    3. 长度≥ 16384，分段编码
    
    参数：
        length: 要编码的长度値
        
    返回：
        编码后的长度字节列表
    """
    assert length < 2**16, "Length must be less than 64K"
    
    if length <= 127:
        return [length.to_bytes(1, byteorder='big')]
    elif length < 2**14:
        # 将第 15 位设为 1，第 14 位设为 0
        return [(length | 2**15).to_bytes(2, byteorder='big')]
    else:
        # 分段编码情况
        counter = length // 2**14
        remainder = length % 2**14
        return [(0b11 << 14 | counter).to_bytes(2, byteorder='big')] + encode_unbound_length(remainder)


def decode_unbound_length(bytes_encoding: bytes) -> int:
    """
    解码无界长度编码。
    
    参数：
        bytes_encoding: 要解码的字节
        
    返回：
        解码后的长度値
    """
    byte_0 = bytes_encoding[0:1]
    encoding = int.from_bytes(byte_0, byteorder='big')
    
    if encoding & 2**7:
        # 长度用两个字节编码
        encoding = int.from_bytes(bytes_encoding[:2], byteorder='big')
        if encoding & 2**15 and encoding & 2**14:
            # 分段编码
            counter = encoding & 0x3F  # 尾部 6 位
            return 2**14 * counter
        elif encoding & 2**15:
            # 去掉第 15 位
            return encoding ^ 2**15
    return encoding


def generate_invalid_length_encoding() -> bytes:
    """
    生成用于测试的非法长度编码。
    
    返回：
        非法长度编码字节
    """
    # 取値范围：0b1100000000000101 到 0b1111111111111111 之间
    return random.randrange(49157, 2**16 - 1).to_bytes(2, byteorder='big')


# ───────────────── 路径适配工具（与 OTABase rrc_utils 对齐） ─────────────────

def remove_embedded_field_indicator(field_path: List[str]) -> List[str]:
    """
    移除嵌入字段标记 '*'。

    仅 OCTET STRING 可能包含嵌入字段，OTABase 使用 '*' 作为标记。
    """
    fp = list(field_path)
    while "*" in fp:
        fp.remove("*")
    return fp


def remove_sequence_of_item_name(field_path: List[str]) -> List[str]:
    """
    移除 SEQUENCE OF item 名称及其指示符。

    OTABase 使用 '^', 后跟 item 名称，表示“回到上层 SEQOF 的元素类型名”。
    对 pycrate 的 get_at() 来说，这两段都应去掉。
    """
    fp = list(field_path)
    while "^" in fp:
        idx = fp.index("^")
        fp.pop(idx)              # 去掉 '^'
        if idx < len(fp):
            fp.pop(idx)          # 再去掉紧随其后的名称
    return fp


def remove_sequence_of_item_indicator(field_path: List[str]) -> List[str]:
    """
    移除 SEQUENCE OF 元素占位符 '__elem__'。

    OTABase 在路径中用 '__elem__' 标记 SEQOF 的具体元素，
    但在 pycrate 的路径中不需要这一层。
    """
    fp = list(field_path)
    while "__elem__" in fp:
        idx = fp.index("__elem__")
        fp.pop(idx)
    return fp


def get_field_type_at_value_path(pkt: Any, val_path: List[Any]):
    """
    沿“值路径”同步走类型，返回路径终点处的 ASN.1 类型对象。
    不依赖 get_at()，故不受 SEQUENCE OF 处 get_at 不消费 path 的影响；
    每条 path 都能唯一确定类型，不捕获异常，有错即抛。

    参数：
        pkt: 已 from_uper 的 pycrate 报文对象
        val_path: get_val_at 可用的值路径（可含 int 下标），即 normalize_field_path_for_get_val_at 的结果

    返回：
        路径终点处的 ASN1Obj 类型对象（与 get_at 等价，但支持 SEQUENCE OF 下标）

    抛出：
        与 get_val_at 相同（invalid value path 等）
    """
    if not val_path:
        return pkt
    type_obj = pkt
    path_so_far: List[Any] = []
    for p in val_path:
        parent_val = pkt.get_val_at(path_so_far) if path_so_far else pkt.get_val()
        t = getattr(type_obj, "TYPE", None)
        if t in ("CHOICE", "OPEN", "ANY"):
            if isinstance(parent_val, tuple) and len(parent_val) == 2:
                key = parent_val[0]
                type_obj = type_obj._cont[key]
            else:
                raise TypeError(f"CHOICE/OPEN/ANY 期望 tuple (key, val)，得到 {type(parent_val)}")
        elif t in ("SEQUENCE OF", "SET OF"):
            type_obj = type_obj._cont
            if not isinstance(parent_val, list):
                raise TypeError(f"SEQUENCE OF 期望 list，path_so_far={path_so_far}, parent_val type={type(parent_val)}")
            if not (isinstance(p, int) and 0 <= p < len(parent_val)):
                raise TypeError(f"SEQUENCE OF 下标越界或非 int，path_so_far={path_so_far}, p={p!r}, len={len(parent_val)}")
        elif t in ("SEQUENCE", "SET", "REAL", "EXT", "EMB PDV", "CHAR STR"):
            type_obj = type_obj._cont[p]
        elif t in ("BIT STRING", "OCTET STRING") and getattr(type_obj, "_const_cont", None) is not None:
            type_obj = type_obj._const_cont
        else:
            raise TypeError(f"未处理的类型 {t}，path_so_far={path_so_far}, p={p!r}")
        path_so_far.append(p)
    return type_obj


def resolve_path_to_match_packet(
    pkt: Any,
    field_path: List[str],
    norm_path: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """
    当 get_at(norm_path) 因 CHOICE 分支与报文不一致而失败时，根据解码后的报文值
    解析出与报文结构一致的路径（在 CHOICE 处用实际 key），使 get_at 能成功。
    与 artifact 一致：artifact 中 path 与 packet 同源故始终有效；我们从文件读 (hex, path)
    时解码后的 CHOICE 可能与 path 中记录分支不一致，通过解析后仍可变异该报文中的对应字段。

    参数：
        pkt: 已 from_uper 的 pycrate 报文对象
        field_path: 原始路径（文件中的 target_path）
        norm_path: 已规范化路径，None 则内部用 normalize_field_path_for_pycrate(field_path)

    返回：
        可与 get_at 配合使用的路径，若无法解析则返回 None
    """
    from pycrate.pycrate_asn1rt.err import ASN1Err

    if norm_path is None:
        norm_path = normalize_field_path_for_pycrate(field_path)
    try:
        pkt.get_at(norm_path)
        return norm_path
    except (ASN1Err, KeyError):
        pass

    resolved: List[Any] = []
    for i in range(len(norm_path)):
        try:
            candidate = resolved + norm_path[i:]
            pkt.get_at(candidate)
            return candidate
        except (ASN1Err, KeyError):
            pass
        prefix = resolved + norm_path[:i]
        try:
            val = pkt.get_val_at(prefix) if prefix else pkt.get_val()
        except Exception:
            return None
        if isinstance(val, tuple) and len(val) == 2 and isinstance(val[0], str):
            resolved.append(val[0])
        else:
            resolved.append(norm_path[i])
    try:
        pkt.get_at(resolved)
        return resolved
    except (ASN1Err, KeyError):
        return None


def normalize_field_path_for_pycrate(field_path: List[str]) -> List[str]:
    """
    将上游记录的“语义路径”转换为 pycrate 可直接用于 get_at() 的路径。

    规则：
      1. 去掉嵌入字段标记 '*'
      2. 去掉 SEQOF item 指示符 '^' 以及其后的 item 类型名
      3. 去掉 '__elem__' 及其紧跟的下标（整数或数字串）：get_at 对 SEQUENCE OF 只做 Obj=Obj._cont，
         下一段必须是元素内字段名，不能是 __elem__ 或数字，否则 _cont["__elem__"] 会报 invalid path。
    得到 [..., listName, fieldName] 形式的类型路径，get_at 可正确走到字段类型。
    若需对“值”做 get_val_at/set_val_at，请使用 normalize_field_path_for_get_val_at()。
    """
    fp = remove_embedded_field_indicator(field_path)
    fp = remove_sequence_of_item_name(fp)
    out: List[str] = []
    i = 0
    while i < len(fp):
        if fp[i] == "__elem__":
            i += 1
            if i < len(fp):
                n = fp[i]
                if isinstance(n, int) or (isinstance(n, str) and str(n).strip().isdigit()):
                    i += 1
        else:
            out.append(fp[i])
            i += 1
    return out


def normalize_field_path_for_get_val_at(field_path: List[str], default_index: int = 0) -> List[Any]:
    """
    将“语义路径”转为 pycrate get_val_at() / set_val_at() 可用的“值路径”。
    与 artifact/test-case-generator/rrc 完全一致：
      - 生成时 path 为 [..., listName, '__elem__', i, ...]，i 为整数下标。
      - 此处只删掉 '__elem__'，保留下标 i（若紧跟的为数字则转为 int），
        得到 [..., listName, i, ...]，供 get_val_at 使用。
      - 若 __elem__ 后无下标（旧 payload），则用 default_index。
    返回的 path 中可能包含 int，类型为 List[Any]。
    """
    fp = remove_embedded_field_indicator(field_path)
    fp = remove_sequence_of_item_name(fp)
    out: List[Any] = []
    i = 0
    while i < len(fp):
        if fp[i] == "__elem__":
            i += 1
            if i < len(fp):
                n = fp[i]
                if isinstance(n, int):
                    out.append(n)
                    i += 1
                elif str(n).strip().isdigit():
                    out.append(int(n))
                    i += 1
                else:
                    out.append(default_index)
            else:
                out.append(default_index)
        else:
            out.append(fp[i])
            i += 1
    return out


def get_path_value(message: Dict[str, Any], path: List[str]) -> Any:
    """
    通过路径获取嵌套字典中的値。
    
    参数：
        message: RRC 消息字典
        path:    大键形成的路径列表
        
    返回：
        指定路径处的値
    """
    current = message
    for key in path:
        if isinstance(current, tuple):
            # 处理 CHOICE 类型：(choice_name, choice_value)
            if current[0] == key:
                current = current[1]
            else:
                raise KeyError(f"CHOICE 不匹配：期望 {key}，实际为 {current[0]}")
        elif isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            # 用整数索引遍历 SEQUENCE OF
            if isinstance(key, int):
                current = current[key]
            else:
                raise TypeError(f"列表索引必须为整数，实际类型：{type(key)}")
        else:
            raise TypeError(f"无法遍历类型 {type(current)}")
    return current


def set_path_value(message: Dict[str, Any], path: List[str], value: Any) -> Dict[str, Any]:
    """
    通过路径设置嵌套字典中的値。
    
    参数：
        message: RRC 消息字典
        path:    大键形成的路径列表
        value:   要设置的値
        
    返回：
        修改后的消息字典
    """
    if not path:
        return value
    
    current = message
    for i, key in enumerate(path[:-1]):
        if isinstance(current, tuple):
            # 处理 CHOICE 类型
            if current[0] == key:
                # 进入 CHOICE 的内容部分
                current = current[1]
            else:
                raise KeyError(f"CHOICE 不匹配：期望 {key}，实际为 {current[0]}")
        elif isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            if isinstance(key, int):
                current = current[key]
            else:
                raise TypeError(f"列表索引必须为整数，实际类型：{type(key)}")
        else:
            raise TypeError(f"无法遍历类型 {type(current)}")
    
    # 设置最终字段的値
    final_key = path[-1]
    if isinstance(current, dict):
        current[final_key] = value
    elif isinstance(current, tuple):
        # 对于元组，需要替换整个元组
        if current[0] == final_key:
            # 返回修改后的元组
            return (current[0], value)
    elif isinstance(current, list):
        if isinstance(final_key, int):
            current[final_key] = value
    
    return message


def calculate_bit_length(lower_bound: int, upper_bound: int) -> int:
    """
    计算表示受约束整数所需的比特数。
    
    参数：
        lower_bound: 范围下界
        upper_bound: 范围上界
        
    返回：
        所需的比特数
    """
    range_size = upper_bound - lower_bound
    if range_size == 0:
        return 0
    return math.floor(math.log2(range_size)) + 1
