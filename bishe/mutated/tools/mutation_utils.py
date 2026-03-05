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
