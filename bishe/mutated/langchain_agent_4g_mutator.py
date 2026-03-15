"""
langchain_agent_4g_mutator — 4G LTE RRC 批量变异 & LangChain Agent 入口

对 bishe/generate_new/output_4g 下的合法 4G LTE RRC payload 进行批量变异，
或通过 LangChain Agent 与 LLM 交互式调用变异工具。

使用方法：
    # 方式 1：批量变异（推荐，无需 API Key）
    #   读取 generate_new/output_4g/rrc_legitimate_payloads*.txt
    #   自动识别字段类型 → 调用对应变异工具 → 输出到 mutate_output_4g/
    python -m bishe.mutated.langchain_agent_4g_mutator --batch

    # 方式 2：批量变异，限制每个文件最多处理 100 行
    python -m bishe.mutated.langchain_agent_4g_mutator --batch --limit 100

    # 方式 3：仅识别字段类型，不执行变异
    python -m bishe.mutated.langchain_agent_4g_mutator --batch --inspect-only

    # 方式 4：直接调用工具演示（无需 API Key）
    python -m bishe.mutated.langchain_agent_4g_mutator

    # 方式 5：通过 LangChain Agent 交互（需要 OPENAI_API_KEY）
    python -m bishe.mutated.langchain_agent_4g_mutator --agent

    # 方式 6：在代码中导入使用
    from bishe.mutated.langchain_agent_4g_mutator import run_batch_mutate
    stats = run_batch_mutate(limit_per_file=100)

    # 或直接调用底层工具函数
    from bishe.mutated.tools import mutate_integer, inspect_field_type
    results = mutate_integer(uper_hex, message_type, target_path, seed=42)

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
    mutate_integer,
    mutate_octet_string,
    mutate_bit_string,
    mutate_sequence_of,
    inspect_field_type,
)

# 批量变异：tool_name -> 实际变异函数
_RUN_MUTATE = {
    "integer_mutation": mutate_integer,
    "octet_string_mutation": mutate_octet_string,
    "bit_string_mutation": mutate_bit_string,
    "sequence_of_mutation": mutate_sequence_of,
}

# ---------------------------------------------------------------------------
# Pydantic 输入 Schema（LangChain StructuredTool 需要）
# ---------------------------------------------------------------------------

class FieldTypeInspectorInput(BaseModel):
    uper_hex: str = Field(
        description="合法 RRC 消息的 UPER 十六进制编码字符串"
    )
    target_path: List[str] = Field(
        description=(
            "目标字段的完整路径列表，"
            "例如 ['message', 'c1', 'dlInformationTransfer-r15', 'refDays-r15']"
        )
    )


class IntegerMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 RRC 消息的 UPER 十六进制编码字符串，例如 '0a501a2ba8a181f05b'"
    )
    message_type: str = Field(
        description="RRC 消息类型字符串，例如 'dlInformationTransfer'"
    )
    target_path: List[str] = Field(
        description=(
            "目标 INTEGER 字段的完整路径列表，"
            "例如 ['message', 'c1', 'dlInformationTransfer-r15', 'refDays-r15']"
        )
    )
    seed: Optional[int] = Field(default=None, description="随机种子，用于复现（可选）")


class OctetStringMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 RRC 消息的 UPER 十六进制编码字符串"
    )
    message_type: str = Field(description="RRC 消息类型字符串")
    target_path: List[str] = Field(
        description="目标 OCTET STRING 字段的完整路径列表"
    )
    seed: Optional[int] = Field(default=None, description="随机种子（可选）")


class BitStringMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 RRC 消息的 UPER 十六进制编码字符串"
    )
    message_type: str = Field(description="RRC 消息类型字符串")
    target_path: List[str] = Field(
        description="目标 BIT STRING 字段的完整路径列表"
    )
    seed: Optional[int] = Field(default=None, description="随机种子（可选）")


class SequenceOfMutationInput(BaseModel):
    uper_hex: str = Field(
        description="合法 RRC 消息的 UPER 十六进制编码字符串"
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
    result = inspect_field_type(
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
    results = mutate_integer(
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
    results = mutate_octet_string(
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
    results = mutate_bit_string(
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
    results = mutate_sequence_of(
        uper_hex=uper_hex,
        message_type=message_type,
        target_path=target_path,
        seed=seed,
    )
    return _serialize_results(results)


# ---------------------------------------------------------------------------
# 构建 LangChain Agent（内部再导入 langchain，便于 --batch 时不加载）
# ---------------------------------------------------------------------------

def build_agent(
    model: str = "gpt-4o",
    temperature: float = 0,
    timeout_s: int = 20,
    max_retries: int = 1,
):
    """
    构建一个绑定了四种 RRC 变异工具的 LangChain ReAct Agent。

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
        name="inspect_field_type",
        description=(
            "检测 RRC 消息中指定路径字段的 ASN.1 类型。"
            "输入合法消息的 UPER 十六进制编码（uper_hex）和字段路径（target_path），"
            "返回包含以下字段的 JSON 对象："
            "field_type（ASN.1 类型名称）、"
            "tool_name（对应变异工具名称，如 integer_mutation）、"
            "supported（是否支持变异：true/false）、"
            "path（点分路径字符串）、"
            "constraint（约束摘要）。"
            "在调用任何变异工具之前，如果不确定字段类型，请先调用此工具。"
        ),
        args_schema=FieldTypeInspectorInput,
    )
    integer_tool = StructuredTool.from_function(
        func=_run_integer_mutation,
        name="integer_mutation",
        description=(
            "对 RRC 消息中的 INTEGER 字段执行比特流级 BASE 策略变异。"
            "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path），"
            "约束信息由工具自动从 pycrate 读取，无需手动提供。"
            "生成 3 条变异：① 合法随机值；② 比特全1溢出；③ 上界+1溢出。"
            "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
        ),
        args_schema=IntegerMutationInput,
    )
    octet_string_tool = StructuredTool.from_function(
        func=_run_octet_string_mutation,
        name="octet_string_mutation",
        description=(
            "对 RRC 消息中的 OCTET STRING 字段执行比特流级 BASE 策略变异。"
            "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path）。"
            "有约束时生成 4 条变异，无约束时生成 22 条变异，约束信息自动解析。"
            "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
        ),
        args_schema=OctetStringMutationInput,
    )
    bit_string_tool = StructuredTool.from_function(
        func=_run_bit_string_mutation,
        name="bit_string_mutation",
        description=(
            "对 RRC 消息中的 BIT STRING 字段执行比特流级 BASE 策略变异。"
            "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path）。"
            "有约束时生成 4 条变异，无约束时生成 12 条变异，约束信息自动解析。"
            "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
        ),
        args_schema=BitStringMutationInput,
    )
    sequence_of_tool = StructuredTool.from_function(
        func=_run_sequence_of_mutation,
        name="sequence_of_mutation",
        description=(
            "对 RRC 消息中的 SEQUENCE OF 字段执行比特流级 BASE 策略变异。"
            "输入合法消息的 UPER 十六进制编码（uper_hex）、消息类型（message_type）和字段路径（target_path）。"
            "生成 4 条变异：长度头为 0、实际元素数、随机值、maxe，内容字节保持不变。"
            "返回 JSON 数组，每项为 [mutated_uper_hex, message_type, target_path]。"
        ),
        args_schema=SequenceOfMutationInput,
    )
    ALL_TOOLS = [field_type_tool, integer_tool, octet_string_tool, bit_string_tool, sequence_of_tool]

    system_prompt = (
        "你是一个 LTE RRC 协议模糊测试专家，能够使用 BASE 策略对 RRC 消息字段进行比特流级变异。\n"
        "你共拥有五个工具：\n"
        "  1. inspect_field_type  —— 检测指定路径字段的 ASN.1 类型及对应变异工具名称\n"
        "  2. integer_mutation    —— 对 INTEGER 字段执行变异（自动读取约束）\n"
        "  3. octet_string_mutation —— 对 OCTET STRING 字段执行变异（自动读取约束）\n"
        "  4. bit_string_mutation —— 对 BIT STRING 字段执行变异（自动读取约束）\n"
        "  5. sequence_of_mutation —— 对 SEQUENCE OF 字段执行变异（自动读取约束）\n"
        "\n"
        "工作流程：\n"
        "  Step 1：若字段类型未知，先调用 inspect_field_type 获取 field_type 和 tool_name。\n"
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

    使用来自测试文件的真实 UPER 数据：
      - INTEGER:    dlInformationTransfer，字段 refDays-r15（lb=0, ub=72999）
      - OCTET STRING: mobilityFromEUTRACommand，字段 si（无约束）
    """
    # ── INTEGER 变异演示 ────────────────────────────────────────────────────
    # print("=" * 60)
    # print("直接调用 integer_mutation 工具")
    # print("字段: dlInformationTransfer / refDays-r15 (INTEGER, lb=0, ub=72999)")
    # print("=" * 60)
    # result = _run_integer_mutation(
    #     uper_hex="0a501a2ba8a181f05b",
    #     message_type="dlInformationTransfer",
    #     target_path=[
    #         "message", "c1", "dlInformationTransfer",
    #         "criticalExtensions", "c1", "dlInformationTransfer-r15", "timeReferenceInfo-r15",
    #         "time-r15", "refDays-r15",
    #     ],
    #     seed=42,
    # )
    # print(result)

    # ── OCTET STRING 变异演示 ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("直接调用 octet_string_mutation 工具")
    print("字段: mobilityFromEUTRACommand / systemInformation.si（无约束 OCTET STRING）")
    print("=" * 60)
    result = _run_octet_string_mutation(
        uper_hex=(
            "0220a61a1e100f3f6139bc5330e49a8c3e03f26ab1b74de1e2005939225c669d4bf88d73288380"
        ),
        message_type="csfbParametersResponseCDMA2000",
        target_path=[
            "message","c1","csfbParametersResponseCDMA2000",
            "criticalExtensions","csfbParametersResponseCDMA2000-r8",
            "mobilityParameters"
        ],
        seed=42,
    )
    # 只打印前 3 条，避免输出过多
    parsed = json.loads(result)
    print(f"共生成 {len(parsed)} 条变异，全部的为：")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))

    # # ── BIT STRING 变异演示 ─────────────────────────────────────────────────
    # print("\n" + "=" * 60)
    # print("直接调用 bit_string_mutation 工具")
    # print("字段: dlInformationTransfer / dedicatedInfoNAS（作为占位演示，实际字段需按需替换）")
    # print("=" * 60)
    # # 该演示仅展示调用方式，若字段类型不匹配会抛出 TypeError
    # try:
    #     result = _run_bit_string_mutation(
    #         uper_hex="0a501a2ba8a181f05b",
    #         message_type="dlInformationTransfer",
    #         target_path=[
    #             "message", "c1", "dlInformationTransfer",
    #             "criticalExtensions", "c1", "dlInformationTransfer-r8",
    #             "dedicatedInfoType", "dedicatedInfoNAS",
    #         ],
    #         seed=42,
    #     )
    #     print(result)
    # except TypeError as e:
    #     print(f"[预期错误] {e}（请替换为 BIT STRING 类型字段路径）")


# ---------------------------------------------------------------------------
# 使用 Agent 与 LLM 交互的示例
# ---------------------------------------------------------------------------

# 测试使用的方法，手动调用大模型,需要API Key
def demo_agent_interaction():
    """
    通过 LangChain ReAct Agent（需要 OPENAI_API_KEY）与工具交互。
    """
    agent = build_agent(model="gpt-4o", temperature=0)

    user_message = (
        "请对以下 RRC 消息中的 INTEGER 字段 refDays-r15 进行变异，"
        "消息类型为 dlInformationTransfer，"
        "UPER 编码为 0a501a2ba8a181f05b，"
        "字段路径为 ['message', 'c1', 'dlInformationTransfer', "
        "'criticalExtensions', 'c1', 'dlInformationTransfer-r15', "
        "'timeReferenceInfo-r15', 'time-r15', 'refDays-r15']。"
    )

    print("发送给 Agent 的消息:")
    print(user_message)
    print()

    response = agent.invoke({"messages": [{"role": "user", "content": user_message}]})

    last_msg = response["messages"][-1]
    print("\nAgent 回答:")
    print(last_msg.content)


# ---------------------------------------------------------------------------
# 批量变异：读取 rrc_legitimate_payloads*.txt → 识别类型 → 变异 → 写入 mutate_output_4g
# ---------------------------------------------------------------------------

# 默认路径：bishe/generate_new/output_4g、bishe/mutated/mutate_output_4g
DEFAULT_PAYLOAD_INPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_new", "output_4g",
)
DEFAULT_MUTATE_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "mutate_output_4g",
)


def run_batch_mutate(
    input_dir: str = DEFAULT_PAYLOAD_INPUT_DIR,
    output_dir: str = DEFAULT_MUTATE_OUTPUT_DIR,
    limit_per_file: Optional[int] = None,
) -> dict:
    """
    读取 input_dir 下所有 rrc_legitimate_payloads 开头的 .txt，
    对每一行：先 inspect_field_type，再按类型调用对应变异工具，
    将变异结果写入 output_dir，每输入文件对应一个输出文件。

    输入文件每行格式：idx, uper_hex, message_type, path_component_1, path_component_2, ...
    输出文件格式与输入文件一致：
      第一行为总条数
      之后每行：序号,hex,message_type,path...,field_type,mutation_strategy_idx

    Args:
        input_dir: 存放 rrc_legitimate_payloads*.txt 的目录
        output_dir: 变异结果输出目录（不存在则创建）
        limit_per_file: 每个文件最多处理行数，None 表示全部

    Returns:
        统计信息 {"files_read": N, "lines_processed": N, "mutations_written": N, "errors": N, "by_file": {...}}
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

                # 识别过程若报错（如 get_at 路径无效）直接抛异常，不捕获，让程序停止
                info = inspect_field_type(uper_hex=uper_hex, target_path=target_path)

                if info.get("supported") != "true" or info.get("tool_name") not in _RUN_MUTATE:
                    continue

                # 使用与报文一致的路径做变异（若识别时做过 resolve 则用 path_for_mutation，避免 CHOICE 分支不一致导致变异报错）
                path_for_mutation = info.get("path_for_mutation", target_path)
                if isinstance(path_for_mutation, str):
                    path_for_mutation = [path_for_mutation]
                mut_fn = _RUN_MUTATE[info["tool_name"]]
                # 有错就抛，不捕获，便于排查
                results = mut_fn(
                    uper_hex=uper_hex,
                    message_type=message_type,
                    target_path=path_for_mutation,
                    seed=None,
                )

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
    input_dir: str = DEFAULT_PAYLOAD_INPUT_DIR,
    limit_per_file: Optional[int] = None,
) -> dict:
    """
    仅做类型识别：遍历所有 payload 行，对每条调用 inspect_field_type，不调用变异。
    不捕获异常，任一行识别失败即抛错。用于验证能否识别出全部路径类型。
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
                info = inspect_field_type(uper_hex=uper_hex, target_path=target_path)
                count += 1
                total += 1
        by_file[basename] = count
    return {"lines_identified": total, "by_file": by_file, "files_read": len(payload_files)}


if __name__ == "__main__":
    import sys

    if "--batch" in sys.argv:
        # 批量变异：读取 output_4g 下 rrc_legitimate_payloads*.txt，输出到 mutate_output_4g
        limit = None
        if "--limit" in sys.argv:
            i = sys.argv.index("--limit")
            if i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
        if "--inspect-only" in sys.argv:
            stats = run_batch_inspect_only(
                limit_per_file=limit,
                input_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generate_new", "output_4g"),
            )
            print("Inspect-only stats:", json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            stats = run_batch_mutate(limit_per_file=limit)
            print("Batch mutate stats:", json.dumps(stats, ensure_ascii=False, indent=2))
    elif "--agent" in sys.argv:
        # 需要设置 OPENAI_API_KEY 环境变量
        demo_agent_interaction()
    else:
        # 无需 API Key，直接调用工具演示
        demo_direct_tool_calls()
