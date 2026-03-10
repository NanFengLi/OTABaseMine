"""
OCTET STRING 变异工具测试模板

使用来自 rrc_legitimate_payloads.txt 的真实合法 RRC 消息，
对其中的 OCTET STRING 字段执行比特流级变异并验证结果。

测试消息:mobilityFromEUTRACommand
目标字段:purpose.handover.systemInformation.si(OCTET STRING，无约束)
"""
import sys
import os

# ── 路径设置 ──────────────────────────────────────────────────────────────────
# 确保从项目根目录运行:python -m bishe.mutated.test.test_octet_string_mutate
# 或者直接:cd <project_root> && python bishe/mutated/test/test_octet_string_mutate.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bishe.mutated.tools.octet_string_mutation import mutate_octet_string

# ── 测试数据(来自 rrc_legitimate_payloads.txt 第 1 条) ───────────────────────
# 原始格式:index,uper_hex,message_type,path1,...,pathN
UPER_HEX = (
    "0220a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d73288380"
    "02a0a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d732883c400a0d4d1405e1c2c35e6ff0d9720f0e7186e1e0fd1a76b0775a7184ebe695da0a0"
)

MESSAGE_TYPE = "csfbParametersResponseCDMA2000"

TARGET_PATH = [
    "message",
    "c1",
    "csfbParametersResponseCDMA2000",
    "criticalExtensions",
    "csfbParametersResponseCDMA2000-r8",
    "mobilityParameters"
]

# ── 辅助打印 ──────────────────────────────────────────────────────────────────

def print_separator(char="─", width=70):
    print(char * width)


def show_original():
    """打印原始消息信息"""
    print_separator("═")
    print("【原始合法消息】")
    print(f"  消息类型  : {MESSAGE_TYPE}")
    print(f"  目标路径  : {' → '.join(TARGET_PATH)}")
    print(f"  UPER(hex) : {UPER_HEX[:40]}...(共 {len(UPER_HEX)//2} 字节)")
    print_separator("═")


def show_results(results):
    """打印变异结果"""
    print(f"\n共生成 {len(results)} 个变异\n")
    print_separator()
    print(f"{'编号':>4}  {'变异后长度(字节)':>14}  {'原始长度(字节)':>12}  {'长度差':>6}  变异 Hex(前20字节)")
    print_separator()

    orig_len = len(UPER_HEX) // 2

    for i, (mut_hex, msg_type, path) in enumerate(results, 1):
        mut_len  = len(mut_hex) // 2
        delta    = mut_len - orig_len
        delta_s  = f"{delta:+d}"
        preview  = mut_hex[:40] + ("..." if len(mut_hex) > 40 else "")
        print(f"{i:>4}  {mut_len:>14}  {orig_len:>12}  {delta_s:>6}  {preview}")

    print_separator()


# ── 主测试流程 ────────────────────────────────────────────────────────────────

def main():
    show_original()

    print("\n正在执行 OCTET STRING 变异(无约束模式，预期 22 条)...")
    try:
        results = mutate_octet_string(
            uper_hex     = UPER_HEX,
            message_type = MESSAGE_TYPE,
            target_path  = TARGET_PATH,
            seed         = 42,          # 固定种子，保证结果可复现
        )
    except Exception as e:
        print(f"[ERROR] 变异失败: {e}")
        import traceback; traceback.print_exc()
        return

    show_results(results)

    # ── 可选:将结果写入文件(取消注释以启用) ────────────────────────────────
    # OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "octet_string_mutations.txt")
    # with open(OUTPUT_FILE, "w") as f:
    #     for mut_hex, msg_type, path in results:
    #         line = ",".join([mut_hex, msg_type] + list(path))
    #         f.write(line + "\n")
    # print(f"\n变异结果已写入 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
