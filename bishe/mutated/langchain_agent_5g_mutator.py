"""
langchain_agent_5g_mutator using 5G NR RRC Mutation Tools

将 bishe/mutated/tools 下的四种 5G NR RRC 字段变异工具封装为 LangChain StructuredTool，
并构建一个可以调用这些工具的 Agent。

使用方法：
    # 方式 1：直接调用工具演示（无需 API Key）
    python -m bishe.mutated.langchain_agent_5g_mutator

    # 方式 2：通过 LangChain Agent 交互（需要 OPENAI_API_KEY）
    python -m bishe.mutated.langchain_agent_5g_mutator --agent

    # 方式 3：在代码中导入使用
    from bishe.mutated.langchain_agent_5g_mutator import build_agent, ALL_TOOLS

    # 构建 Agent 并调用
    agent = build_agent(model="gpt-4o", temperature=0)
    response = agent.invoke({"messages": [{"role": "user", "content": "..."}]})

    # 或直接调用底层工具函数（无需 LLM）
    from bishe.mutated.tools import mutate_octet_string_5g, inspect_field_type_5g
    results = mutate_octet_string_5g(uper_hex, message_type, target_path, seed=42)

新接口（比特流替换方式）：
    工具输入：uper_hex（完整消息 UPER 十六进制）+ message_type + target_path + seed
    工具输出：JSON 数组，每项为 [mutated_uper_hex, message_type, [path...]]
    约束参数（lower_bound/upper_bound/constrained）由工具内部从 pycrate 自动解析，无需外部传入。

环境变量（需在 .env 中配置，仅 Agent 模式需要）：
    OPENAI_API_KEY:  OpenAI API Key
    OPENAI_BASE_URL: 自定义 API 地址（可选，用于代理或国内镜像）
"""

import json
import os
from typing import List, Optional

from dotenv import load_dotenv

# 使用 python-dotenv 自动加载当前工作目录下的 .env
load_dotenv()


from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from bishe.mutated.tools import (
    mutate_integer_5g,
    mutate_octet_string_5g,
    mutate_bit_string_5g,
    mutate_sequence_of_5g,
    inspect_field_type_5g,
)

# ---------------------------------------------------------------------------
# Pydantic 输入 Schema（LangChain StructuredTool 需要）
# ---------------------------------------------------------------------------
# 继承BaseModel类，那么运行时强制检查字段类型是否符合str和List[str]
class FieldTypeInspectorInput(BaseModel):
    uper_hex: str = Field(
        description="合法 5G NR RRC 消息的 UPER 十六进制编码字符串"
    )
    target_path: List[str] = Field(
        description=(
            "目标字段的完整路径列表，"
            "例如 ['message', 'c1', 'rrcReconfiguration', 'criticalExtensions', "
            "'rrcReconfiguration', 'secondaryCellGroup']"
        )
    )


class IntegerMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 5G NR RRC 消息的 UPER 十六进制编码字符串"
    )
    message_type: str = Field(
        description="RRC 消息类型字符串，例如 'rrcReconfiguration'"
    )
    target_path: List[str] = Field(
        description=(
            "目标 INTEGER 字段的完整路径列表，"
            "例如 ['message', 'c1', 'rrcReconfiguration', 'criticalExtensions', "
            "'rrcReconfiguration', 'rrc-TransactionIdentifier']"
        )
    )
    seed: Optional[int] = Field(default=None, description="随机种子，用于复现（可选）")


class OctetStringMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 5G NR RRC 消息的 UPER 十六进制编码字符串"
    )
    message_type: str = Field(description="RRC 消息类型字符串")
    target_path: List[str] = Field(
        description="目标 OCTET STRING 字段的完整路径列表"
    )
    seed: Optional[int] = Field(default=None, description="随机种子（可选）")


class BitStringMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 5G NR RRC 消息的 UPER 十六进制编码字符串"
    )
    message_type: str = Field(description="RRC 消息类型字符串")
    target_path: List[str] = Field(
        description="目标 BIT STRING 字段的完整路径列表"
    )
    seed: Optional[int] = Field(default=None, description="随机种子（可选）")


class SequenceOfMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 5G NR RRC 消息的 UPER 十六进制编码字符串"
    )
    message_type: str = Field(description="RRC 消息类型字符串")
    target_path: List[str] = Field(
        description="目标 SEQUENCE OF 字段的完整路径列表"
    )
    seed: Optional[int] = Field(default=None, description="随机种子（可选）")


# ---------------------------------------------------------------------------
# 工具函数包装器（将结果序列化为 JSON 字符串，方便 LLM 处理）
# ---------------------------------------------------------------------------

def _run_inspect_field_type(
    uper_hex: str,
    target_path: List[str],
) -> str:
    result = inspect_field_type_5g(
        uper_hex=uper_hex,
        target_path=target_path,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


def _serialize_results(results: list) -> str:
    """将 mutate_xxx 返回的 List[Tuple[str, str, List[str]]] 序列化为 JSON。

    每个元素由 (mutated_uper_hex, message_type, target_path) 三元组组成，
    序列化后格式为：
        [
          ["<hex>", "<message_type>", ["path", "item", ...]],
          ...
        ]
    """
    serialized = [
        [mut_hex, msg_type, list(path)]
        for mut_hex, msg_type, path in results
    ]
    return json.dumps(serialized, ensure_ascii=False, indent=2)


def _run_integer_mutation(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> str:
    results = mutate_integer_5g(
        uper_hex=uper_hex,
        message_type=message_type,
        target_path=target_path,
        seed=seed,
    )
    return _serialize_results(results)


def _run_octet_string_mutation(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> str:
    results = mutate_octet_string_5g(
        uper_hex=uper_hex,
        message_type=message_type,
        target_path=target_path,
        seed=seed,
    )
    return _serialize_results(results)


def _run_bit_string_mutation(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> str:
    results = mutate_bit_string_5g(
        uper_hex=uper_hex,
        message_type=message_type,
        target_path=target_path,
        seed=seed,
    )
    return _serialize_results(results)


def _run_sequence_of_mutation(
    uper_hex: str,
    message_type: str,
    target_path: List[str],
    seed: Optional[int] = None,
) -> str:
    results = mutate_sequence_of_5g(
        uper_hex=uper_hex,
        message_type=message_type,
        target_path=target_path,
        seed=seed,
    )
    return _serialize_results(results)


# ---------------------------------------------------------------------------
# 注册为 LangChain StructuredTool
# ---------------------------------------------------------------------------

field_type_tool = StructuredTool.from_function(
    func=_run_inspect_field_type,
    name="inspect_field_type_5g",
    description=(
        "检测 5G NR RRC 消息中指定路径字段的 ASN.1 类型。"
        "输入合法消息的 UPER 十六进制编码（uper_hex）和字段路径（target_path），"
        "返回包含以下字段的 JSON 对象："
        "field_type（ASN.1 类型名称）、"
        "tool_name（对应变异工具名称，如 integer_mutation_5g）、"
        "supported（是否支持变异：true/false）、"
        "path（点分路径字符串）、"
        "constraint（约束摘要）。"
        "在调用任何变异工具之前，如果不确定字段类型，请先调用此工具。"
    ),
    args_schema=FieldTypeInspectorInput,
)

integer_tool = StructuredTool.from_function(
    func=_run_integer_mutation,
    name="integer_mutation_5g",
    description=(
        "对 5G NR RRC 消息中的 INTEGER 字段执行比特流级 BASE 策略变异。"
        "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path），"
        "约束信息由工具自动从 pycrate 读取，无需手动提供。"
        "生成 3 条变异：① 合法随机值；② 比特全1溢出；③ 上界+1溢出。"
        "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
    ),
    args_schema=IntegerMutationInput,
)

octet_string_tool = StructuredTool.from_function(
    func=_run_octet_string_mutation,
    name="octet_string_mutation_5g",
    description=(
        "对 5G NR RRC 消息中的 OCTET STRING 字段执行比特流级 BASE 策略变异。"
        "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path）。"
        "有约束时生成 4 条变异，无约束时生成 22 条变异，约束信息自动解析。"
        "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
    ),
    args_schema=OctetStringMutationInput,
)

bit_string_tool = StructuredTool.from_function(
    func=_run_bit_string_mutation,
    name="bit_string_mutation_5g",
    description=(
        "对 5G NR RRC 消息中的 BIT STRING 字段执行比特流级 BASE 策略变异。"
        "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path）。"
        "有约束时生成 4 条变异，无约束时生成 12 条变异，约束信息自动解析。"
        "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
    ),
    args_schema=BitStringMutationInput,
)

sequence_of_tool = StructuredTool.from_function(
    func=_run_sequence_of_mutation,
    name="sequence_of_mutation_5g",
    description=(
        "对 5G NR RRC 消息中的 SEQUENCE OF 字段执行比特流级 BASE 策略变异。"
        "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path）。"
        "生成 4 条变异：长度头为 0、实际元素数、随机值、maxe，内容字节保持不变。"
        "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
    ),
    args_schema=SequenceOfMutationInput,
)

# 所有工具列表（inspect_field_type 排在最前，便于 Agent 优先发现）
ALL_TOOLS = [field_type_tool, integer_tool, octet_string_tool, bit_string_tool, sequence_of_tool]


# ---------------------------------------------------------------------------
# 构建 LangChain Agent
# ---------------------------------------------------------------------------

def build_agent(
    model: str = "gpt-4o",
    temperature: float = 0,
    timeout_s: int = 20,
    max_retries: int = 1,
):
    """
    构建一个绑定了四种 5G NR RRC 变异工具的 LangChain ReAct Agent。

    Args:
        model: OpenAI 模型名称，默认 gpt-4o
        temperature: 模型温度
        timeout_s: 单次请求超时秒数
        max_retries: 请求失败最大重试次数

    Returns:
        CompiledStateGraph，调用方式：
            agent.invoke({"messages": [{"role": "user", "content": "..."}]})

    环境变量（从 .env 自动加载）:
        OPENAI_API_KEY: OpenAI API Key
        OPENAI_BASE_URL (可选): 自定义 API 地址（用于代理或国内镜像）
    """
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise EnvironmentError(
            "未找到 OPENAI_API_KEY，请确认 .env 文件已配置或环境变量已设置。"
        )

    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_s,
        max_retries=max_retries,
    )

    system_prompt = (
        "你是一个 5G NR RRC 协议模糊测试专家，能够使用 BASE 策略对 RRC 消息字段进行比特流级变异。\n"
        "你共拥有五个工具：\n"
        "  1. inspect_field_type_5g  —— 检测指定路径字段的 ASN.1 类型及对应变异工具名称\n"
        "  2. integer_mutation_5g    —— 对 INTEGER 字段执行变异（自动读取约束）\n"
        "  3. octet_string_mutation_5g —— 对 OCTET STRING 字段执行变异（自动读取约束）\n"
        "  4. bit_string_mutation_5g —— 对 BIT STRING 字段执行变异（自动读取约束）\n"
        "  5. sequence_of_mutation_5g —— 对 SEQUENCE OF 字段执行变异（自动读取约束）\n"
        "\n"
        "工作流程：\n"
        "  Step 1：若字段类型未知，先调用 inspect_field_type_5g 获取 field_type 和 tool_name。\n"
        "  Step 2：根据 tool_name 调用对应的变异工具，传入 uper_hex、message_type、target_path。\n"
        "  Step 3：汇报生成的变异数量及每条变异的十六进制编码（摘要）。\n"
        "\n"
        "所有变异工具只需三个必要参数（uper_hex、message_type、target_path），\n"
        "约束（上界/下界/是否受约束）由工具内部自动从 ASN.1 规范解析，无需手动提供。"
    )

    return create_agent(model=llm, tools=ALL_TOOLS, system_prompt=system_prompt)


# ---------------------------------------------------------------------------
# 快速演示：直接调用工具（无需 LLM）
# ---------------------------------------------------------------------------

def demo_direct_tool_calls():
    """
    直接调用工具函数演示，无需 OpenAI API Key。

    使用 5G NR RRC 的真实 UPER 数据：
      - OCTET STRING: rrcReconfiguration / lateNonCriticalExtension（无约束，CONTAINING）
      - OCTET STRING: rrcReconfiguration / secondaryCellGroup（无约束，CONTAINING）
    """
    # # ── OCTET STRING 变异演示（lateNonCriticalExtension）─────────────────────
    # print("=" * 60)
    # print("直接调用 octet_string_mutation_5g 工具")
    # print("字段: rrcReconfiguration / lateNonCriticalExtension（无约束 OCTET STRING）")
    # print("=" * 60)
    # result = _run_octet_string_mutation(
    #     uper_hex="02100800",
    #     message_type="rrcReconfiguration",
    #     target_path=[
    #         "message", "c1", "rrcReconfiguration",
    #         "criticalExtensions", "rrcReconfiguration",
    #         "lateNonCriticalExtension",
    #     ],
    #     seed=42,
    # )
    # parsed = json.loads(result)
    # print(f"共生成 {len(parsed)} 条变异，前 3 条为：")
    # for i, item in enumerate(parsed[:3], 1):
    #     print(f"  变异 {i}: hex={item[0][:40]}... (len={len(item[0])})")

    # ── OCTET STRING 变异演示（secondaryCellGroup）──────────────────────────
    print("\n" + "=" * 60)
    print("直接调用 octet_string_mutation_5g 工具")
    print("字段: rrcReconfiguration / secondaryCellGroup（无约束 OCTET STRING）")
    print("=" * 60)
    result = _run_octet_string_mutation(
        uper_hex="0240100400",
        message_type="rrcReconfiguration",
        target_path=[
            "message", "c1", "rrcReconfiguration",
            "criticalExtensions", "rrcReconfiguration",
            "secondaryCellGroup",
        ],
        seed=42,
    )
    parsed = json.loads(result)
    print(f"共生成 {len(parsed)} 条变异，全部的为：")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 使用 Agent 与 LLM 交互的示例
# ---------------------------------------------------------------------------


agent = build_agent(model="gpt-4o", temperature=0)

# 测试使用的方法，手动调用大模型,需要API Key
def demo_agent_interaction():
    """
    通过 LangChain ReAct Agent（需要 OPENAI_API_KEY）与工具交互。
    """
    agent = build_agent(model="gpt-4o", temperature=0)

    user_message = (
        "请对以下 5G NR RRC 消息中的 OCTET STRING 字段 lateNonCriticalExtension 进行变异，"
        "消息类型为 rrcReconfiguration，"
        "UPER 编码为 02100800，"
        "字段路径为 ['message', 'c1', 'rrcReconfiguration', "
        "'criticalExtensions', 'rrcReconfiguration', 'lateNonCriticalExtension']。"
    )

    print("发送给 Agent 的消息:")
    print(user_message)
    print()

    response = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    last_msg = response["messages"][-1]
    print("\nAgent 回答:")
    print(last_msg.content)


if __name__ == "__main__":
    import sys

    if "--agent" in sys.argv:
        # 需要设置 OPENAI_API_KEY 环境变量
        demo_agent_interaction()
    else:
        # 无需 API Key，直接调用工具演示
        demo_direct_tool_calls()
