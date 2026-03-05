"""
字段类型检测工具测试

验证 inspect_field_type() 对不同 ASN.1 类型字段的识别结果：
  - INTEGER      → dlInformationTransfer / refDays-r15
  - OCTET STRING → csfbParametersResponseCDMA2000 / mobilityParameters（有约束）
  - BIT STRING   → dlInformationTransfer / refQuarterMicroSeconds-r15（SIZE(2)）
  - SEQUENCE OF  → rrcConnectionReconfiguration / measObjectToAddModList

每个用例打印返回字典并断言 field_type / tool_name 正确。
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bishe.mutated.tools.field_type_inspector import inspect_field_type

# ── 颜色 / 格式辅助 ───────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def ok(msg):  print(f"  {GREEN}✓ {msg}{RESET}")
def fail(msg): print(f"  {RED}✗ {msg}{RESET}"); raise AssertionError(msg)
def sep(title=""): print(f"\n{'─'*68}\n  {YELLOW}{title}{RESET}" if title else "─"*68)

# ── 测试用例定义 ──────────────────────────────────────────────────────────────

TEST_CASES = [
    # ── 1. INTEGER ──────────────────────────────────────────────────────────
    {
        "label":       "INTEGER — dlInformationTransfer / refDays-r15 (lb=0, ub=72999)",
        "uper_hex":    "0a501a2ba8a181f05b",
        "target_path": [
            "message", "c1", "dlInformationTransfer",
            "criticalExtensions", "c1", "dlInformationTransfer-r15",
            "timeReferenceInfo-r15", "time-r15", "refDays-r15",
        ],
        "expect_type": "INTEGER",
        "expect_tool": "integer_mutation",
    },
    # ── 2. INTEGER (不同约束，同一消息) ──────────────────────────────────────
    {
        "label":       "INTEGER — dlInformationTransfer / refSeconds-r15 (lb=0, ub=86399)",
        "uper_hex":    "0a501a2ba8a181f05b",
        "target_path": [
            "message", "c1", "dlInformationTransfer",
            "criticalExtensions", "c1", "dlInformationTransfer-r15",
            "timeReferenceInfo-r15", "time-r15", "refSeconds-r15",
        ],
        "expect_type": "INTEGER",
        "expect_tool": "integer_mutation",
    },
    # ── 3. OCTET STRING (有约束 SIZE(0..255)) ────────────────────────────────
    {
        "label":       "OCTET STRING — csfbParametersResponseCDMA2000 / mobilityParameters (SIZE 0..255)",
        "uper_hex":    (
            "0220a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d73288380"
            "02a0a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d732883c4"
            "00a0d4d1405e1c2c35e6ff0d9720f0e7186e1e0fd1a76b0775a7184ebe695da0a0"
        ),
        "target_path": [
            "message", "c1", "csfbParametersResponseCDMA2000",
            "criticalExtensions",
            "csfbParametersResponseCDMA2000-r8",
            "mobilityParameters",
        ],
        "expect_type": "OCTET STRING",
        "expect_tool": "octet_string_mutation",
    },
    # ── 4. BIT STRING (有约束 SIZE(32)) ─────────────────────────────────────
    {
        "label":       "BIT STRING — csfbParametersResponseCDMA2000 / rand (SIZE 32)",
        "uper_hex":    (
            "0220a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d73288380"
            "02a0a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d732883c4"
            "00a0d4d1405e1c2c35e6ff0d9720f0e7186e1e0fd1a76b0775a7184ebe695da0a0"
        ),
        "target_path": [
            "message", "c1", "csfbParametersResponseCDMA2000",
            "criticalExtensions",
            "csfbParametersResponseCDMA2000-r8",
            "rand",
        ],
        "expect_type": "BIT STRING",
        "expect_tool": "bit_string_mutation",
    },
    # ── 5. SEQUENCE OF ───────────────────────────────────────────────────────
    {
        "label":       "SEQUENCE OF — rrcConnectionReconfiguration / measObjectToAddModList",
        "uper_hex":    "261010005e1440a984808195aa95d05080fc660400",
        "target_path": [
            "message", "c1", "rrcConnectionReconfiguration",
            "criticalExtensions", "c1", "rrcConnectionReconfiguration-r8",
            "measConfig", "measObjectToAddModList",
        ],
        "expect_type": "SEQUENCE OF",
        "expect_tool": "sequence_of_mutation",
    },
]

# ── 主测试逻辑 ────────────────────────────────────────────────────────────────

def run_test(case: dict) -> bool:
    sep(case["label"])
    try:
        result = inspect_field_type(
            uper_hex=case["uper_hex"],
            target_path=case["target_path"],
        )
    except Exception as e:
        print(f"  {RED}调用异常: {e}{RESET}")
        return False

    # 打印完整返回值
    print("  返回值：")
    for k, v in result.items():
        print(f"    {k:12s}: {v}")

    # 断言
    passed = True
    if result["field_type"] != case["expect_type"]:
        print(f"  {RED}✗ field_type 期望 '{case['expect_type']}' 但得到 '{result['field_type']}'{RESET}")
        passed = False
    else:
        ok(f"field_type == '{result['field_type']}'")

    if result["tool_name"] != case["expect_tool"]:
        print(f"  {RED}✗ tool_name 期望 '{case['expect_tool']}' 但得到 '{result['tool_name']}'{RESET}")
        passed = False
    else:
        ok(f"tool_name  == '{result['tool_name']}'")

    if result["supported"] != "true":
        print(f"  {RED}✗ supported 期望 'true' 但得到 '{result['supported']}'{RESET}")
        passed = False
    else:
        ok(f"supported  == 'true'")

    if result["constraint"] in ("", None):
        print(f"  {YELLOW}⚠ constraint 为空{RESET}")
    else:
        ok(f"constraint == '{result['constraint']}'")

    return passed


def run_manual_path_test():
    """
    手动错路径测试：传入一个根节点路径（非叶子节点），
    验证工具能抛出合适的异常而不崩溃。
    """
    sep("异常路径测试 — 传入非叶子节点路径")
    try:
        result = inspect_field_type(
            uper_hex="0a501a2ba8a181f05b",
            target_path=["message", "c1"],  # 非叶子节点
        )
        print("  返回值（非叶子节点）：", result)
        ok("未抛出异常，返回了结果（field_type 可能为复合类型）")
        return True
    except Exception as e:
        print(f"  {YELLOW}⚠ 抛出异常（符合预期）: {type(e).__name__}: {e}{RESET}")
        return True  # 异常本身也是可接受结果


def main():
    print("\n" + "=" * 68)
    print("  inspect_field_type() 工具测试")
    print("=" * 68)

    results = []
    for case in TEST_CASES:
        results.append(run_test(case))

    # 非叶子节点鲁棒性测试（不计入通过/失败统计）
    run_manual_path_test()

    # 汇总
    sep()
    passed = sum(results)
    total  = len(results)
    color  = GREEN if passed == total else RED
    print(f"\n  {color}通过 {passed}/{total} 个测试用例{RESET}\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
