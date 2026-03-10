"""
RRC 协议类型和上下文管理

支持 4G LTE (EUTRA) 和 5G NR 两种 RRC 协议的切换。
通过 RRCContext 封装协议相关的 ASN.1 对象，使生成器代码无需关心具体协议。
"""
from enum import Enum


class RATType(Enum):
    """无线接入技术类型"""
    LTE_4G = "4g"
    NR_5G = "5g"


class RRCContext:
    """
    封装协议相关的 RRC 对象

    根据 RAT 类型（4G/5G）延迟加载对应的 ASN.1 模块，
    并提供统一的接口访问 DL-DCCH-Message 和 GLOBAL 模块。
    """

    def __init__(self, rat: RATType):
        self.rat = rat
        if rat == RATType.LTE_4G:
            from bishe.pycrate_asn1obj.eutran_4g import RRCLTE
            self.dl_dcch_message = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
            self.global_mod = RRCLTE.GLOBAL.MOD['EUTRA-RRC-Definitions']
        elif rat == RATType.NR_5G:
            from bishe.pycrate_asn1obj.nr_5g import RRCNR
            self.dl_dcch_message = RRCNR.NR_RRC_Definitions.DL_DCCH_Message
            self.global_mod = RRCNR.GLOBAL.MOD['NR-RRC-Definitions']

    @property
    def output_subdir(self):
        """返回对应协议的输出子目录名"""
        return "output_4g" if self.rat == RATType.LTE_4G else "output_5g"
