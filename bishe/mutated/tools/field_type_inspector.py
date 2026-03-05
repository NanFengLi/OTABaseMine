"""
字段类型检测工具

根据合法 UPER 十六进制消息与字段路径，自动识别目标字段的 ASN.1 类型，
返回字符串标签，供 Agent 选择对应的变异工具。

支持识别的类型（与四种变异工具一一对应）：
  "INTEGER"        → 使用 integer_mutation
  "OCTET STRING"   → 使用 octet_string_mutation
  "BIT STRING"     → 使用 bit_string_mutation
  "SEQUENCE OF"    → 使用 sequence_of_mutation
  "UNKNOWN:<TYPE>" → 无对应变异工具，TYPE 为 pycrate 原始类型字符串

接口：
  inspect_field_type(uper_hex, target_path) -> dict
"""

from typing import Dict, List

from pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT   = True

from pycrate_asn1dir import RRCLTE

# 支持的类型 → 对应变异工具名
_SUPPORTED: Dict[str, str] = {
    "INTEGER":     "integer_mutation",
    "OCTET STRING": "octet_string_mutation",
    "BIT STRING":   "bit_string_mutation",
    "SEQUENCE OF":  "sequence_of_mutation",
}


def inspect_field_type(
    uper_hex: str,
    target_path: List[str],
) -> Dict[str, str]:
    """
    从合法 UPER 十六进制消息中解析目标字段的 ASN.1 类型。

    参数：
        uper_hex:    合法消息的 UPER 十六进制编码字符串
        target_path: 目标字段路径列表，与 mutate_xxx 保持一致

    返回：字典，包含以下字段
        "field_type"  : ASN.1 类型字符串，如 "INTEGER"、"OCTET STRING" 等
        "tool_name"   : 对应变异工具名称，不支持时为 "UNSUPPORTED"
        "supported"   : "true" 或 "false"（字符串，便于 LLM 处理）
        "path"        : 点分路径字符串，便于确认
        "constraint"  : 约束信息摘要字符串（有则列出，无则为 "none"）

    示例返回：
        {
            "field_type": "INTEGER",
            "tool_name":  "integer_mutation",
            "supported":  "true",
            "path":       "message.c1.dlInformationTransfer.refDays-r15",
            "constraint": "lb=0, ub=72999"
        }
    """
    pkt = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    fld = pkt.get_at(target_path)
    fld.set_val(pkt.get_val_at(target_path))

    raw_type: str = fld.TYPE  # pycrate 原始类型字符串

    # 归一化：pycrate 有时使用 "BIT STRING" / "OCTET STRING"（含空格）
    normalized = raw_type.strip()

    tool_name = _SUPPORTED.get(normalized, "UNSUPPORTED")
    supported  = "true" if tool_name != "UNSUPPORTED" else "false"

    # 约束摘要
    constraint = _describe_constraint(fld, normalized)

    return {
        "field_type": normalized,
        "tool_name":  tool_name,
        "supported":  supported,
        "path":       ".".join(target_path),
        "constraint": constraint,
    }


def _describe_constraint(fld, field_type: str) -> str:
    """生成字段约束的可读摘要字符串。"""
    try:
        if field_type == "INTEGER":
            cv = fld._const_val
            if cv is not None:
                return f"lb={cv.lb}, ub={cv.ub}"
            return "none"

        if field_type in ("OCTET STRING", "BIT STRING"):
            cs = fld._const_sz
            if cs is not None:
                return f"lb={cs.lb}, ub={cs.ub} ({'bits' if field_type == 'BIT STRING' else 'bytes'})"
            return "unconstrained"

        if field_type == "SEQUENCE OF":
            cs = fld._const_sz
            if cs is not None:
                return f"minItems={cs.lb}, maxItems={cs.ub}"
            return "unconstrained"

    except Exception:
        pass
    return "none"
