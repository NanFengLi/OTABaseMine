"""
langchain_agent_5g_mutator — 5G NR RRC 批量变异 & LangChain Agent 入口

对 bishe/generate_new/output_5g 下的合法 5G NR RRC payload 进行批量变异，
或通过 LangChain Agent 与 LLM 交互式调用变异工具。

使用方法：
    # 方式 1：批量变异（推荐，无需 API Key）
    python -m bishe.mutated.langchain_agent_5g_mutator --batch

    # 方式 2：限制每个文件最多处理 100 行
    python -m bishe.mutated.langchain_agent_5g_mutator --batch --limit 100

    # 方式 3：无约束 OCTET STRING / BIT STRING 每条消息仅随机挑选 4 种策略
    python -m bishe.mutated.langchain_agent_5g_mutator --batch --max-strategies 4

    # 方式 4：仅识别字段类型，不执行变异
    python -m bishe.mutated.langchain_agent_5g_mutator --batch --inspect-only

    # 方式 5：直接调用工具演示（无需 API Key）
    python -m bishe.mutated.langchain_agent_5g_mutator

    # 方式 6：通过 LangChain Agent 交互（需要 OPENAI_API_KEY）
    python -m bishe.mutated.langchain_agent_5g_mutator --agent

命令行参数：
    --batch              批量变异模式
    --limit N            每个文件最多处理 N 行
    --max-strategies N   无约束 OCTET STRING（22 条）/ BIT STRING（12 条）
                         每条消息随机挑选 N 种策略变异（默认全部使用）
    --inspect-only       仅识别字段类型，不执行变异
    --agent              LangChain Agent 交互模式（需要 OPENAI_API_KEY）

变异策略数量：
    INTEGER            — 2 条（比特全1溢出、上界+1溢出）
    OCTET STRING 受约束 — 4 条
    OCTET STRING 无约束 — 22 条（可通过 --max-strategies 限制）
    BIT STRING 受约束   — 4 条
    BIT STRING 无约束   — 12 条（可通过 --max-strategies 限制）
    SEQUENCE OF        — 4 条

批量变异输出格式：
    第一行：总条数
    之后每行：<序号>,<变异后hex>,<消息类型>,<字段路径>,<字段类型>,<变异策略编号>

环境变量（仅 Agent 模式需要，在 .env 中配置）：
    OPENAI_API_KEY:  OpenAI API Key
    OPENAI_BASE_URL: 自定义 API 地址（可选，用于代理或国内镜像）
"""

import json
import os
from typing import List, Optional

from dotenv import load_dotenv

# 使用 python-dotenv 自动加载当前工作目录下的 .env
load_dotenv()


from pydantic import BaseModel, Field

from bishe.mutated.tools import (
    mutate_integer_5g,
    mutate_octet_string_5g,
    mutate_bit_string_5g,
    mutate_sequence_of_5g,
    inspect_field_type_5g,
)

# 批量变异：tool_name -> 实际变异函数（与 4G 一致）
_RUN_MUTATE = {
    "integer_mutation_5g": mutate_integer_5g,
    "octet_string_mutation_5g": mutate_octet_string_5g,
    "bit_string_mutation_5g": mutate_bit_string_5g,
    "sequence_of_mutation_5g": mutate_sequence_of_5g,
}

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
    from langchain.agents import create_agent
    from langchain_core.tools import StructuredTool
    from langchain_openai import ChatOpenAI

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

    ALL_TOOLS = [field_type_tool, integer_tool, octet_string_tool, bit_string_tool, sequence_of_tool]

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


# ---------------------------------------------------------------------------
# 批量变异：读取 rrc_legitimate_payloads*.txt → 识别类型 → 变异 → 写入 mutate_output_5g（与 4G 逻辑一致）
# ---------------------------------------------------------------------------

DEFAULT_PAYLOAD_INPUT_DIR_5G = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_new", "output_5g",
)
DEFAULT_MUTATE_OUTPUT_DIR_5G = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "mutate_output_5g",
)


def run_batch_mutate(
    input_dir: str = DEFAULT_PAYLOAD_INPUT_DIR_5G,
    output_dir: str = DEFAULT_MUTATE_OUTPUT_DIR_5G,
    limit_per_file: Optional[int] = None,
    max_strategies: Optional[int] = None,
) -> dict:
    """
    读取 input_dir 下所有 rrc_legitimate_payloads 开头的 .txt，
    对每一行：先 inspect_field_type_5g，再按类型调用对应变异工具，
    将变异结果写入 output_dir，每输入文件对应一个输出文件。

    Args:
        max_strategies: 无约束 OCTET STRING / BIT STRING 每条消息随机挑选的最大策略数（None 表示全部使用）
    """
    os.makedirs(output_dir, exist_ok=True)

    payload_files = sorted([
        f for f in os.listdir(input_dir)
        if f.startswith("rrc_legitimate_payloads") and f.endswith(".txt")
    ])
    if not payload_files:
        return {"error": f"No rrc_legitimate_payloads*.txt in {input_dir}", "files_read": 0}

    stats = {"files_read": 0, "lines_processed": 0, "mutations_written": 0, "errors": 0, "by_file": {}}

    for basename in payload_files:
        in_path = os.path.join(input_dir, basename)
        out_name = basename.replace(".txt", "_mutations.txt")
        out_path = os.path.join(output_dir, out_name)
        file_stats = {"lines": 0, "mutations": 0, "errors": 0}

        mutations_lines = []
        with open(in_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                if limit_per_file is not None and file_stats["lines"] >= limit_per_file:
                    break
                parts = line.split(",")
                if len(parts) < 4:
                    continue
                try:
                    idx = parts[0].strip()
                    uper_hex = parts[1].strip()
                    message_type = parts[2].strip()
                    target_path = [p.strip() for p in parts[3:]]
                except Exception:
                    file_stats["errors"] += 1
                    stats["errors"] += 1
                    continue

                file_stats["lines"] += 1
                stats["lines_processed"] += 1

                info = inspect_field_type_5g(uper_hex=uper_hex, target_path=target_path)

                if info.get("supported") != "true" or info.get("tool_name") not in _RUN_MUTATE:
                    continue

                path_for_mutation = info.get("path_for_mutation", target_path)
                if isinstance(path_for_mutation, str):
                    path_for_mutation = [path_for_mutation]
                mut_fn = _RUN_MUTATE[info["tool_name"]]
                mut_kwargs = dict(
                    uper_hex=uper_hex,
                    message_type=message_type,
                    target_path=path_for_mutation,
                    seed=None,
                )
                if max_strategies is not None and info["tool_name"] in (
                    "octet_string_mutation_5g", "bit_string_mutation_5g",
                ):
                    mut_kwargs["max_strategies"] = max_strategies
                results = mut_fn(**mut_kwargs)

                path_csv = ",".join(str(p) for p in target_path)
                field_type = info.get("field_type", "")
                for strategy_idx, (mut_hex, _msg_type, _path) in enumerate(results, 1):
                    mutations_lines.append(
                        ",".join([mut_hex, message_type, path_csv, field_type, str(strategy_idx)])
                    )
                    file_stats["mutations"] += 1
                    stats["mutations_written"] += 1

        stats["by_file"][basename] = file_stats
        stats["files_read"] += 1

        with open(out_path, "w", encoding="utf-8") as out:
            out.write(str(len(mutations_lines)) + "\n")
            for i, ml in enumerate(mutations_lines, 1):
                out.write(str(i) + "," + ml + "\n")

    return stats


def run_batch_inspect_only(
    input_dir: str = DEFAULT_PAYLOAD_INPUT_DIR_5G,
    limit_per_file: Optional[int] = None,
) -> dict:
    """
    仅做类型识别：遍历所有 payload 行，对每条调用 inspect_field_type_5g，不调用变异。
    不捕获异常，任一行识别失败即抛错。与 4G run_batch_inspect_only 一致。
    """
    payload_files = sorted([
        f for f in os.listdir(input_dir)
        if f.startswith("rrc_legitimate_payloads") and f.endswith(".txt")
    ])
    if not payload_files:
        return {"error": f"No rrc_legitimate_payloads*.txt in {input_dir}", "lines_identified": 0}

    total = 0
    by_file = {}
    for basename in payload_files:
        in_path = os.path.join(input_dir, basename)
        count = 0
        with open(in_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if limit_per_file is not None and count >= limit_per_file:
                    break
                parts = line.split(",")
                if len(parts) < 4:
                    continue
                idx, uper_hex, message_type = parts[0].strip(), parts[1].strip(), parts[2].strip()
                target_path = [p.strip() for p in parts[3:]]
                info = inspect_field_type_5g(uper_hex=uper_hex, target_path=target_path)
                count += 1
                total += 1
        by_file[basename] = count
    return {"lines_identified": total, "by_file": by_file, "files_read": len(payload_files)}


if __name__ == "__main__":
    import sys

    if "--batch" in sys.argv:
        # 批量变异：读取 output_5g 下 rrc_legitimate_payloads*.txt，输出到 mutate_output_5g（与 4G 一致）
        limit = None
        if "--limit" in sys.argv:
            i = sys.argv.index("--limit")
            if i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
        max_strat = None
        if "--max-strategies" in sys.argv:
            i = sys.argv.index("--max-strategies")
            if i + 1 < len(sys.argv):
                max_strat = int(sys.argv[i + 1])
        if "--inspect-only" in sys.argv:
            stats = run_batch_inspect_only(
                limit_per_file=limit,
                input_dir=DEFAULT_PAYLOAD_INPUT_DIR_5G,
            )
            print("Inspect-only stats:", json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            stats = run_batch_mutate(limit_per_file=limit, max_strategies=max_strat)
            print("Batch mutate stats:", json.dumps(stats, ensure_ascii=False, indent=2))
    elif "--agent" in sys.argv:
        # 需要设置 OPENAI_API_KEY 环境变量
        demo_agent_interaction()
    else:
        # 无需 API Key，直接调用工具演示
        demo_direct_tool_calls()
