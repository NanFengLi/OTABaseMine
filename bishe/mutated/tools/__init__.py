"""
RRC 消息变异工具包

提供针对不同 RRC 字段类型的变异策略，
基于 OTABase BASE 变异策略实现。

统一接口：
    mutate_xxx(uper_hex, message_type, target_path, seed=None)
    -> List[(mutated_uper_hex, message_type, target_path)]

4G LTE 版本：mutate_xxx / inspect_field_type
5G NR 版本：mutate_xxx_5g / inspect_field_type_5g
"""

from .integer_mutation import mutate_integer
from .octet_string_mutation import mutate_octet_string
from .bit_string_mutation import mutate_bit_string
from .sequence_of_mutation import mutate_sequence_of
from .field_type_inspector import inspect_field_type

from .integer_mutation_5g import mutate_integer_5g
from .octet_string_mutation_5g import mutate_octet_string_5g
from .bit_string_mutation_5g import mutate_bit_string_5g
from .sequence_of_mutation_5g import mutate_sequence_of_5g
from .field_type_inspector_5g import inspect_field_type_5g

__all__ = [
    # 4G LTE
    'mutate_integer',
    'mutate_octet_string',
    'mutate_bit_string',
    'mutate_sequence_of',
    'inspect_field_type',
    # 5G NR
    'mutate_integer_5g',
    'mutate_octet_string_5g',
    'mutate_bit_string_5g',
    'mutate_sequence_of_5g',
    'inspect_field_type_5g',
]