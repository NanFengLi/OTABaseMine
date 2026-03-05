"""
RRC 变异 Agent 交互式运行脚本

用法:
    # 方式1：交互式对话（循环输入）
    python -m bishe.mutated.run_agent

    # 方式2：单次问一个问题
    python -m bishe.mutated.run_agent --once "请对 rrc-TransactionIdentifier 字段进行变异"

    # 方式3：直接调用工具（不走 LLM，速度快）
    python -m bishe.mutated.run_agent --direct
"""

import argparse
import json
from bishe.mutated.langchain_agent import (
    ALL_TOOLS,
    build_agent,
    _run_integer_mutation,
    _run_octet_string_mutation,
    _run_bit_string_mutation,
    _run_sequence_of_mutation,
)

# ---------------------------------------------------------------------------
# 示例 RRC 消息（用于演示和直接调用模式）
# ---------------------------------------------------------------------------

EXAMPLE_MESSAGE = {
    "message": (
        "c1",
        (
            "csfbParametersResponseCDMA2000",
            {
                "rrc-TransactionIdentifier": 0,
                "criticalExtensions": (
                    "csfbParametersResponseCDMA2000-r8",
                    {
                        "rand": (0, 32),
                        "mobilityParameters": b"\x00",
                        "nonCriticalExtension": {
                            "lateNonCriticalExtension": b"\x00"
                        },
                    },
                ),
            },
        ),
    )
}

# ---------------------------------------------------------------------------
# 直接调用工具模式（无需 LLM）
# ---------------------------------------------------------------------------

def run_direct():
    """无需 API Key，直接调用四种变异工具演示。"""

    print("=" * 60)
    print("模式：直接调用工具（不走 LLM）")
    print("=" * 60)

    # 1. INTEGER 字段变异
    print("\n[1] INTEGER 变异 —— rrc-TransactionIdentifier（范围 0-3）")
    result = _run_integer_mutation(
        message=EXAMPLE_MESSAGE,
        target_path=["message", "c1", "csfbParametersResponseCDMA2000",
                     "rrc-TransactionIdentifier"],
        lower_bound=0,
        upper_bound=3,
        message_type="csfbParametersResponseCDMA2000",
        seed=42,
    )
    data = json.loads(result)
    print(f"  生成变异数：{data['count']}")
    for i, desc in enumerate(data.get("descriptions", []), 1):
        print(f"  变异 {i}: {desc}")
    print(f"  UPER 编码（hex）:")
    for mutation in data["mutations"]:
        print(f"    {mutation}")

    # 2. BIT_STRING 字段变异
    print("\n[2] BIT_STRING 变异 —— rand（32 位固定长度）")
    result = _run_bit_string_mutation(
        message=EXAMPLE_MESSAGE,
        target_path=["message", "c1", "csfbParametersResponseCDMA2000",
                     "criticalExtensions", "csfbParametersResponseCDMA2000-r8", "rand"],
        message_type="csfbParametersResponseCDMA2000",
        constrained=True,
        lower_bound=32,
        upper_bound=32,
        current_value_int=0,
        current_value_bits=32,
        seed=42,
    )
    data = json.loads(result)
    print(f"  生成变异数：{data['count']}")
    for i, m in enumerate(data["mutations"], 1):
        print(f"  变异 {i}: {m.get('mutation_type','?')} — {m.get('mutation_description','')}")

    # 3. OCTET_STRING 字段变异
    print("\n[3] OCTET_STRING 变异 —— mobilityParameters（长度 0-255 字节）")
    result = _run_octet_string_mutation(
        message=EXAMPLE_MESSAGE,
        target_path=["message", "c1", "csfbParametersResponseCDMA2000",
                     "criticalExtensions", "csfbParametersResponseCDMA2000-r8",
                     "mobilityParameters"],
        message_type="csfbParametersResponseCDMA2000",
        constrained=True,
        lower_bound=0,
        upper_bound=255,
        current_value_hex="00",
        seed=42,
    )
    data = json.loads(result)
    print(f"  生成变异数：{data['count']}")
    for i, m in enumerate(data["mutations"], 1):
        print(f"  变异 {i}: {m.get('mutation_type','?')} — {m.get('mutation_description','')}")

    print("\n完成。所有变异结果均为 ASN.1 UPER 编码后的 hex 字符串，可直接发送到 UE。")


# ---------------------------------------------------------------------------
# Agent 模式：构造带结构化参数的提示
# ---------------------------------------------------------------------------

def build_mutation_prompt(field_type: str, field_name: str, path: list,
                           lower: int, upper: int, message_type: str,
                           message: dict) -> str:
    """
    构造一条让 Agent 调用变异工具的提示。
    
    参数说明：
        field_type: INTEGER / OCTET_STRING / BIT_STRING / SEQUENCE_OF
        field_name: 字段名，仅用于描述
        path: 字段路径列表
        lower/upper: 约束范围
        message_type: RRC 消息类型
        message: 完整的 RRC 消息字典
    """
    return (
        f"请对以下 RRC 消息中的 {field_type} 字段 '{field_name}' 进行 BASE 策略变异。\n"
        f"消息类型: {message_type}\n"
        f"字段路径: {path}\n"
        f"约束范围: lower_bound={lower}, upper_bound={upper}\n"
        f"完整消息: {message}\n"
        f"请调用对应的变异工具，返回生成的变异描述。"
    )


def run_agent_once(user_input: str, timeout_s: int = 20):
    """启动 Agent，发送一条消息，打印结果后退出。"""
    print("正在初始化 Agent（连接 LLM）...")
    agent = build_agent(model="gpt-4o", temperature=0, timeout_s=timeout_s, max_retries=1)
    print("Agent 就绪，正在处理...\n")

    try:
        response = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
        last = response["messages"][-1]
        print("Agent 回答：")
        print(last.content)
    except Exception as e:
        print(f"[错误] Agent 调用失败：{e}")
        print("提示：可先用 --direct 验证本地变异逻辑，或增大 --timeout。")


def run_agent_interactive(timeout_s: int = 20):
    """启动 Agent，持续接受用户输入（输入 exit/quit 退出）。"""
    print("正在初始化 Agent（连接 LLM）...")
    agent = build_agent(model="gpt-4o", temperature=0, timeout_s=timeout_s, max_retries=1)
    print("Agent 就绪！输入你的请求，输入 'exit' 退出。\n")

    # 预置示例提示，方便用户参考
    print("示例指令：")
    print("  > 请对 rrc-TransactionIdentifier 字段（INTEGER，范围0-3，消息类型 csfbParametersResponseCDMA2000）进行变异")
    print("  > 对 rand 字段（BIT_STRING，32位固定长度）进行变异")
    print()

    history = []
    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("退出。")
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

        try:
            response = agent.invoke({"messages": history})
            msgs = response["messages"]
            last = msgs[-1]
            print(f"\nAgent: {last.content}\n")
            # 更新完整历史
            history = [{"role": m.type if hasattr(m, "type") else "assistant",
                        "content": m.content} for m in msgs]
        except Exception as e:
            print(f"[错误] {e}\n")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RRC 变异 Agent 运行脚本")
    parser.add_argument("--direct", action="store_true",
                        help="直接调用工具（不走 LLM，无需 API Key）")
    parser.add_argument("--once", type=str, default=None, metavar="PROMPT",
                        help="发送单条消息给 Agent 后退出")
    parser.add_argument("--timeout", type=int, default=20,
                        help="LLM 请求超时秒数，默认 20")
    args = parser.parse_args()

    if args.direct:
        run_direct()
    elif args.once:
        run_agent_once(args.once, timeout_s=args.timeout)
    else:
        run_agent_interactive(timeout_s=args.timeout)
