"""
INTEGER 字段变异工具

基于 OTABase 模糊测试框架，对 RRC 消息中的 INTEGER 类型字段
实现 BASE 变异策略。

参考：OTABase rrc_fuzzer.py - mutate_rrc_integer_field()
"""

import math
import random
from copy import deepcopy
from typing import Any, Dict, List

from bishe.mutated.tools.mutation_utils import calculate_bit_length

# 尝试导入 pycrate 以进行 ASN.1 编码
try:
    from pycrate_asn1dir import RRCLTE
    DL_DCCH_Message = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    PYCRATE_AVAILABLE = True
except ImportError:
    PYCRATE_AVAILABLE = False
    DL_DCCH_Message = None


def mutate_integer_field(
    message: Dict[str, Any],
    target_path: List[str],
    lower_bound: int,
    upper_bound: int,
    message_type: str,
    seed: int = None
) -> List[bytes]:
    """
    使用 BASE 策略对 INTEGER 字段进行变异。

    BASE 策略利用字段所分配的比特数可以表示超出规范约束范围的值的特点。
    例如，若某字段约束为 0-9（规范），但编码使用 4 位，则实际可表示 0-15。

    变异类型：
    1. 范围内随机合法值
    2. 所分配比特数可表示的最大值（比特位溢出）
    3. 上界溢出：upper_bound + 1

    参数：
        message:      完整的 RRC 消息字典
        target_path:  指向目标 INTEGER 字段的路径列表
        lower_bound:  INTEGER 约束下界
        upper_bound:  INTEGER 约束上界
        message_type: RRC 消息类型（如 'csfbParametersResponseCDMA2000'）
        seed:         随机数种子（可选，用于复现）

    返回：
        ASN.1 UPER 编码后的字节列表（每个元素对应一个变异报文）

    示例：
        >>> message = {
        ...     'message': ('c1', ('csfbParametersResponseCDMA2000', {
        ...         'rrc-TransactionIdentifier': 0,
        ...         'criticalExtensions': ('criticalExtensionsFuture', {})
        ...     }))
        ... }
        >>> mutations = mutate_integer_field(
        ...     message=message,
        ...     target_path=['message', 'c1', 'csfbParametersResponseCDMA2000',
        ...                  'rrc-TransactionIdentifier'],
        ...     lower_bound=0,
        ...     upper_bound=3,
        ...     message_type='csfbParametersResponseCDMA2000'
        ... )
        >>> len(mutations)
        3
        >>> all(isinstance(m, bytes) for m in mutations)
        True
    """
    if not PYCRATE_AVAILABLE:
        raise ImportError("需要安装 pycrate 才能执行变异。请执行：pip install pycrate")

    if seed is not None:
        random.seed(seed)

    # 获取 DL-DCCH-Message ASN.1 对象
    packet = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message

    # 禁用边界检查，允许写入超出规范的值
    packet._SAFE_BND = False

    # 设置初始消息值
    packet.set_val(message)

    # 保存初始报文值，用于每次变异前重置
    p = deepcopy(packet._val)

    mutated_packets = []

    # 计算该整数字段实际占用的比特数及最大可表示值
    bit_length = calculate_bit_length(lower_bound, upper_bound)
    max_representable = (2 ** bit_length - 1) + lower_bound

    # 变异 1：范围内随机合法值
    packet.set_val(p)
    random_value = random.randint(lower_bound, upper_bound)
    packet.set_val_at(target_path, random_value)
    mutated_packets.append(packet.to_uper())

    # 变异 2：比特位可表示的最大值（利用比特位分配冗余）
    packet.set_val(p)
    packet.set_val_at(target_path, max_representable)
    mutated_packets.append(packet.to_uper())

    # 变异 3：上界溢出（upper_bound + 1）
    packet.set_val(p)
    overflow_value = upper_bound + 1
    packet.set_val_at(target_path, overflow_value)
    mutated_packets.append(packet.to_uper())

    return mutated_packets


def integer_mutation_tool(
    message: Dict[str, Any],
    target_path: List[str],
    lower_bound: int,
    upper_bound: int,
    message_type: str,
    seed: int = None
) -> Dict[str, Any]:
    """
    INTEGER 字段变异的 Agent 工具接口，应作为 Agent 工具注册使用。

    参数：
        message:      完整的 RRC 消息字典
        target_path:  指向目标 INTEGER 字段的路径列表
        lower_bound:  INTEGER 约束下界
        upper_bound:  INTEGER 约束上界
        message_type: RRC 消息类型
        seed:         随机数种子（可选，用于复现）

    返回：
        包含以下字段的字典：
            - mutations:    ASN.1 UPER 编码后的字节列表
            - count:        生成的变异数量
            - strategy:     使用的变异策略
            - descriptions: 每个变异的描述列表
    """
    mutations = mutate_integer_field(
        message=message,
        target_path=target_path,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        message_type=message_type,
        seed=seed
    )

    # 计算比特长度和最大可表示值，用于生成描述信息
    bit_length = calculate_bit_length(lower_bound, upper_bound)
    max_representable = (2 ** bit_length - 1) + lower_bound

    # 用相同种子重新生成随机值，确保描述与实际变异一致
    if seed is not None:
        random.seed(seed)
    random_value = random.randint(lower_bound, upper_bound)

    descriptions = [
        f'将 INTEGER 设为范围内随机值：{random_value}',
        f'将 INTEGER 设为比特位可表示的最大值：{max_representable}（比特溢出）',
        f'将 INTEGER 设为上界溢出值：{upper_bound + 1}'
    ]

    return {
        'mutations': mutations,      # 字节列表
        'count': len(mutations),
        'strategy': 'BASE',
        'field_type': 'INTEGER',
        'target_path': target_path,
        'message_type': message_type,
        'descriptions': descriptions
    }
