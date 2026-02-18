"""
RRC 合法测试样例生成器的配置文件
"""
import os
from pathlib import Path

# 项目根目录 (OTABaseMine)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 原始 test-case-generator 的路径（用于引用资源）
ORIGINAL_TCG_DIR = PROJECT_ROOT / "artifact" / "test-case-generator"

# ASN.1 定义文件路径（通过 symlink 引用）
RELEASE_LTE_R17_DIR = Path(__file__).parent / "releaseLTE_R17"


class GeneratorConfig:
    """RRC 合法样例生成器配置"""

    # 默认随机种子
    DEFAULT_SEED = 1

    # 生成的 OCTET_STRING 默认长度
    OCTET_STRING_LENGTH = 32

    # 生成的 BIT_STRING 默认长度
    BIT_STRING_LENGTH = 64

    # 最大递归深度（用于展开嵌套的 OCTET STRING containing 其他 IE）
    MAX_RECUR_DEPTH = 0

    # 是否启用可选字段生成
    ENABLE_OPTIONAL = True

    # 默认输出目录
    OUTPUT_DIR = str(Path(__file__).parent / "output")

    # 默认输出文件名
    DEFAULT_OUTPUT_FILE = "rrc_legitimate_payloads.txt"

    # 生成报告文件
    REPORT_FILE = "generation_report.json"

    # 日志级别
    LOG_LEVEL = "INFO"
