"""
RRC 字段类型枚举

定义了 RRC 生成器可以针对的不同目标字段类型。
从 OTABase artifact/test-case-generator/rrc/rrc_fields.py 抽取。
"""
from enum import Enum


class Fields(Enum):
    """
    RRC 目标字段类型枚举

    - BIT_STRING:    可变长度位序列
    - OCTET_STRING:  字节序列和二进制数据
    - INTEGER:       各种约束范围内的数值
    - SEQOF:         重复元素的序列
    """
    BIT_STRING = 1
    OCTET_STRING = 2
    INTEGER = 3
    SEQOF = 4

    @classmethod
    def from_name(cls, name: str) -> 'Fields':
        """通过字符串名称获取枚举值"""
        mapping = {
            'BIT_STRING': cls.BIT_STRING,
            'OCTET_STRING': cls.OCTET_STRING,
            'INTEGER': cls.INTEGER,
            'SEQOF': cls.SEQOF,
        }
        if name not in mapping:
            raise ValueError(f"未知的字段类型: {name}，可选: {list(mapping.keys())}")
        return mapping[name]

    @classmethod
    def all_fields(cls) -> list:
        """返回所有字段类型的列表"""
        return [cls.BIT_STRING, cls.OCTET_STRING, cls.INTEGER, cls.SEQOF]
