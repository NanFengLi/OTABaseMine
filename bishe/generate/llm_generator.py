import logging
import re
from typing import List, Dict, Tuple, Optional
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage

from bishe.generate.rag_db import RAGDatabase
from bishe.generate.prompts import RRC_GENERATION_SYSTEM_PROMPT, RRC_GENERATION_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


def parse_llm_response(response: str) -> Tuple[Optional[str], List[str]]:
    """
    解析 LLM 返回的响应，提取 MESSAGE 和 MISSING 内容
    
    Args:
        response: LLM 返回的完整响应文本
    

    Returns:
        (message_content, missing_types): MESSAGE 标签中的内容和 MISSING 类型列表
    """
    message_content = None
    missing_types = []
    
    # 提取 <MESSAGE> 标签中的内容
    message_match = re.search(r'<MESSAGE>(.*?)</MESSAGE>', response, re.DOTALL)
    if message_match:
        message_content = message_match.group(1).strip()
    
    # 提取 <MISSING> 标签中的内容
    missing_match = re.search(r'<MISSING>(.*?)</MISSING>', response, re.DOTALL)
    if missing_match:
        missing_str = missing_match.group(1).strip()
        if missing_str:  # 如果不为空
            # 按逗号分割，去除空格
            missing_types = [t.strip() for t in missing_str.split(',') if t.strip()]
    
    return message_content, missing_types


def validate_message_encoding(message_code: str) -> Tuple[bool, Optional[str]]:
    """
    验证生成的消息是否能通过 UPER 编码
    
    Args:
        message_code: 生成的 Python 消息代码
    
    Returns:
        (is_valid, error_message): 是否有效和错误信息
    """
    try:
        # 动态导入必要的模块
        from pycrate_asn1dir import RRCLTE
        from binascii import hexlify
        
        # 执行生成的代码，获取消息变量
        local_vars = {}
        exec(message_code, {"__builtins__": __builtins__}, local_vars)
        
        # 查找消息变量（通常是 dl_dcch_message）
        message_var = None
        for var_name, var_value in local_vars.items():
            if isinstance(var_value, dict) and 'message' in var_value:
                message_var = var_value
                break
        
        if message_var is None:
            return False, "未找到有效的消息变量"
        
        # 尝试编码
        DL_DCCH = RRCLTE.EUTRA_RRC_Definitions.DL_DCCH_Message
        DL_DCCH.set_val(message_var)
        encoded = DL_DCCH.to_uper()
        
        # 编码成功
        logger.info(f"消息编码成功: {hexlify(encoded).decode()}")
        return True, None
        
    except Exception as e:
        error_msg = f"编码验证失败: {str(e)}\n 请检查生成的消息内容：{DL_DCCH}"
        logger.error(error_msg)
        return False, error_msg


def create_llm_client(model: str = "gpt-4", temperature: float = 0.7, api_key: Optional[str] = None, base_url: Optional[str] = None):
    """
    创建 LLM 客户端
    
    Args:
        model: 模型名称
        temperature: 温度参数
        api_key: API 密钥（可选，从环境变量读取）
        base_url: API 基础地址（可选）
    
    Returns:
        ChatOpenAI 实例
    """
    kwargs = {
        "temperature": temperature,
    }
    
    if api_key:
        kwargs["api_key"] = api_key
        
    if base_url:
        kwargs["base_url"] = base_url
    
    # 使用 init_chat_model 初始化模型
    # model_provider 显式指定为 'openai'，这样 LangChain 知道该加载哪个具体的实现类
    return init_chat_model(model, **kwargs)


def generate_single_message(
    llm,
    rag_db: RAGDatabase,
    path_info: Dict,
    max_iterations: int = 20
) -> bool:
    """
    为单条路径生成消息（迭代处理 MISSING 类型）
    
    Args:
        llm: LangChain LLM 实例
        rag_db: RAG 数据库实例
        path_info: 路径信息字典
        max_iterations: 最大迭代次数
    
    Returns:
        是否成功生成并验证
    """
    target_path = path_info['path']
    message_type = path_info['top_level_message']  # 例如 'DL_DCCH_Message'
    
    # 初始 ASN.1 定义片段（可以从 RAG 中获取或使用空字符串）
    asn1_snippets = """
    DL-DCCH-Message ::= SEQUENCE {
	    message					DL-DCCH-MessageType
    }
    DL-DCCH-MessageType ::= CHOICE {
        c1						CHOICE {
            csfbParametersResponseCDMA2000			CSFBParametersResponseCDMA2000,
            dlInformationTransfer					DLInformationTransfer,
            handoverFromEUTRAPreparationRequest		HandoverFromEUTRAPreparationRequest,
            mobilityFromEUTRACommand				MobilityFromEUTRACommand,
            rrcConnectionReconfiguration			RRCConnectionReconfiguration,
            rrcConnectionRelease					RRCConnectionRelease,
            securityModeCommand						SecurityModeCommand,
            ueCapabilityEnquiry						UECapabilityEnquiry,
            counterCheck							CounterCheck,
            ueInformationRequest-r9					UEInformationRequest-r9,
            loggedMeasurementConfiguration-r10		LoggedMeasurementConfiguration-r10,
            rnReconfiguration-r10					RNReconfiguration-r10,
            rrcConnectionResume-r13					RRCConnectionResume-r13,
            dlDedicatedMessageSegment-r16			DLDedicatedMessageSegment-r16,
            spare2 NULL, spare1 NULL
        },
        messageClassExtension	SEQUENCE {}
    }
"""
    with open("bishe/generate/doc_version_control/source_asn/36331-j00/message_extracted/RRCConnectionReconfiguration.asn", "r", encoding="utf-8") as f:
        file_content = f.read()
    asn1_snippets += "\n\n" + file_content
    # 保存上一次生成的消息内容
    # 第一轮没有上一次内容，使用"dl_dcch_message = DL-DCCH-Message"作为开始，开始进行转换
    previous_message = "dl_dcch_message = DL-DCCH-Message"

    
    for iteration in range(max_iterations):
        logger.info(f"  迭代 {iteration + 1}/{max_iterations}")
        
        # 构建用户提示
        user_prompt = RRC_GENERATION_USER_PROMPT_TEMPLATE.format(
            asn1_snippets=asn1_snippets,
            # message_type=message_type,
            temp_content=previous_message,
            # target_path=" , ".join(target_path)
            target_path="message,c1,rrcConnectionReconfiguration,criticalExtensions,c1,rrcConnectionReconfiguration-r8,measConfig,measObjectToRemoveList"
        )
        
        # 调用 LLM
        messages = [
            SystemMessage(content=RRC_GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        # 打印发送给LLM的消息内容
        logger.debug("=" * 80)
        logger.debug("发送给LLM的消息:")
        logger.debug("-" * 80)
        for i, msg in enumerate(messages):
            msg_type = "System" if isinstance(msg, SystemMessage) else "Human"
            logger.debug(f"[{msg_type} Message {i+1}]:\n{msg.content}\n")
        logger.debug("=" * 80)
        
        response = llm.invoke(messages)
        response_text = response.content
        logger.info(f"  LLM 响应:\n{response_text}")
        
        # 解析响应
        message_content, missing_types = parse_llm_response(response_text)
        
        if not message_content:
            logger.error("  LLM 未返回有效的 MESSAGE 内容")
            return False
        
        logger.info(f"  第{iteration + 1}轮次生成的消息代码:\n{message_content}")
        
        # 检查是否有缺失类型
        if not missing_types:
            logger.info("  没有缺失类型，开始验证编码...")
            
            # 验证编码
            is_valid, error_msg = validate_message_encoding(message_content)
            
            if is_valid:
                logger.info("  ✓ 消息编码验证通过")
                # TODO: 存储到数据库
                return True
            else:
                logger.error(f"  ✗ 编码验证失败: {error_msg}")
                return False
        
        # 有缺失类型，查询 RAG 数据库
        logger.info(f"  发现缺失类型: {missing_types}")
        
        # 从 RAG 数据库查询缺失类型的定义
        retrieved_snippets = []
        for missing_type in missing_types:
            logger.info(f"  查询 RAG 数据库: {missing_type}")
            results = rag_db.query_asn1(query_texts=[missing_type], n_results=1)
            
            if results:
                retrieved_snippets.extend(results)
                logger.info(f"  找到 {len(results)} 个相关定义")
            else:
                logger.warning(f"  未找到 {missing_type} 的定义")
        
        # 合并 ASN.1 定义片段
        if retrieved_snippets:
            asn1_snippets = "\n\n".join(retrieved_snippets)
        else:
            logger.error("  未能从 RAG 数据库获取缺失类型的定义")
            return False
        
        # 保存当前生成的消息，供下一轮参考
        previous_message = message_content
    
    logger.warning(f"  达到最大迭代次数 {max_iterations}，仍未生成有效消息")
    return False
