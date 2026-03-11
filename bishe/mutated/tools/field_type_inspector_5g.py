"""
5G NR 字段类型检测工具

根据合法 UPER 十六进制消息与字段路径，自动识别目标字段的 ASN.1 类型。
接口与 4G 版本完全一致，仅协议定义替换为 NR RRC。
"""

from typing import Dict, List

from pycrate.pycrate_asn1rt.asnobj import ASN1Obj
ASN1Obj._SAFE_BND = False
ASN1Obj._SILENT   = True

from bishe.pycrate_asn1obj.nr_5g import RRCNR

_SUPPORTED: Dict[str, str] = {
    "INTEGER":      "integer_mutation_5g",
    "OCTET STRING": "octet_string_mutation_5g",
    "BIT STRING":   "bit_string_mutation_5g",
    "SEQUENCE OF":  "sequence_of_mutation_5g",
}


def inspect_field_type_5g(
    uper_hex: str,
    target_path: List[str],
) -> Dict[str, str]:
    """
    从 5G NR RRC 合法 UPER 十六进制消息中解析目标字段的 ASN.1 类型。

    参数：
        uper_hex:    合法消息的 UPER 十六进制编码字符串
        target_path: 目标字段路径列表

    返回：字典，包含 field_type, tool_name, supported, path, constraint
    """
    pkt = RRCNR.NR_RRC_Definitions.DL_DCCH_Message
    pkt.from_uper(bytes.fromhex(uper_hex))

    fld = pkt.get_at(target_path)
    fld.set_val(pkt.get_val_at(target_path))

    raw_type: str = fld.TYPE
    normalized = raw_type.strip()

    tool_name = _SUPPORTED.get(normalized, "UNSUPPORTED")
    supported = "true" if tool_name != "UNSUPPORTED" else "false"

    constraint = _describe_constraint(fld, normalized)

    return {
        "field_type": normalized,
        "tool_name":  tool_name,
        "supported":  supported,
        "path":       ".".join(str(x) for x in target_path),
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
