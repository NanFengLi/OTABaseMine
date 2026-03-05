"""
INTEGER 变异工具测试模板

使用来自 rrc_legitimate_payloads.txt 的真实合法 RRC 消息，
对其中的 INTEGER 字段执行比特流级变异并验证结果。

测试消息：dlInformationTransfer
目标字段：timeReferenceInfo-r15.time-r15.refDays-r15（INTEGER, 0..72999）
"""
import sys
import os
import math

# ── 路径设置 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bishe.mutated.tools.integer_mutation import mutate_integer

# ── 测试数据（来自 rrc_legitimate_payloads.txt 第 1 条） ───────────────────────
# 原始格式：index,uper_hex,message_type,path1,...,pathN
UPER_HEX = "0a501a2ba8a181f05b"

MESSAGE_TYPE = "dlInformationTransfer"

TARGET_PATH = [
    "message",
    "c1",
    "dlInformationTransfer",
    "criticalExtensions",
    "c1",
    "dlInformationTransfer-r15",
    "timeReferenceInfo-r15",
    "time-r15",
    "refDays-r15",
]

# 字段约束信息（来自 LTE ASN.1 规范，供注释对照）
LB = 0        # INTEGER 下界
UB = 72999    # INTEGER 上界
# lbs = floor(log2(UB - LB)) + 1 = floor(log2(72999)) + 1 = 17 位
# max_repr = 2^17 - 1 = 131071（超出 UB=72999，冗余空间溢出）
# overflow = UB + 1 = 73000

# ── 辅助打印 ──────────────────────────────────────────────────────────────────

def print_separator(char="─", width=72):
    print(char * width)


def show_original():
    lbs = math.floor(math.log2(UB - LB)) + 1
    max_repr = 2**lbs - 1
    print_separator("═")
    print("【原始合法消息】")
    print(f"  消息类型   : {MESSAGE_TYPE}")
    print(f"  目标路径   : {' → '.join(TARGET_PATH[-3:])}")
    print(f"  UPER(hex)  : {UPER_HEX}（共 {len(UPER_HEX)//2} 字节）")
    print(f"  字段约束   : INTEGER ({LB}..{UB})")
    print(f"  编码位宽   : {lbs} 位（lbs = floor(log2({UB}-{LB}))+1）")
    print(f"  冗余最大值 : {max_repr}（2^{lbs}-1，超出上界 {max_repr - UB}）")
    print_separator("═")


def show_results(results):
    """打印变异结果，并对照预期变异类型说明"""
    lbs        = math.floor(math.log2(UB - LB)) + 1
    max_repr   = 2**lbs - 1 + LB
    overflow   = UB + 1

    descriptions = [
        f"变异 1 — 范围内随机合法值    [lb={LB}, ub={UB}]",
        f"变异 2 — 比特冗余最大值      编码=2^{lbs}-1, 真实值≈{max_repr}（超出上界 {max_repr-UB}）",
        f"变异 3 — 上界 +1 溢出        值={overflow}（ub+1）",
    ]

    print(f"\n共生成 {len(results)} 个变异（INTEGER 定长编码，包长不变）\n")
    print_separator()
    print(f"{'编号':>4}  {'变异类型说明':<52}  {'变异后长度(字节)':>8}  {'前10字节 Hex'}")
    print_separator()

    orig_len = len(UPER_HEX) // 2
    for i, (mut_hex, msg_type, path) in enumerate(results, 1):
        mut_len = len(mut_hex) // 2
        delta   = mut_len - orig_len
        delta_s = f"({delta:+d})" if delta != 0 else "(不变)"
        preview = mut_hex[:20]
        desc    = descriptions[i - 1] if i <= len(descriptions) else ""
        print(f"{i:>4}  {desc:<52}  {mut_len:>5}{delta_s:<6}  {preview}")

    print_separator()


# ── 主测试流程 ────────────────────────────────────────────────────────────────

def main():
    show_original()

    print("\n正在执行 INTEGER 变异（预期 3 条）...")
    try:
        results = mutate_integer(
            uper_hex     = UPER_HEX,
            message_type = MESSAGE_TYPE,
            target_path  = TARGET_PATH,
            seed         = 42,     # 固定种子，保证变异 1 的随机值可复现
        )
    except Exception as e:
        print(f"[ERROR] 变异失败: {e}")
        import traceback; traceback.print_exc()
        return

    show_results(results)

    # ── 可选：将结果写入文件（取消注释以启用）────────────────────────────────
    # OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "integer_mutations.txt")
    # with open(OUTPUT_FILE, "w") as f:
    #     for mut_hex, msg_type, path in results:
    #         line = ",".join([mut_hex, msg_type] + list(path))
    #         f.write(line + "\n")
    # print(f"\n变异结果已写入 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
