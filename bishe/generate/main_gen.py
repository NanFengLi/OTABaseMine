import sys
import os
import logging
import argparse


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if project_root not in sys.path:
    sys.path.append(project_root)


artifact_rrc_path = os.path.join(project_root, "artifact/test-case-generator")
if artifact_rrc_path not in sys.path:
    sys.path.append(artifact_rrc_path)

# 移除顶层导入，避免 -h 响应慢
# from bishe.generate.path_manager import PathManager, TargetType
# from bishe.generate.rag_db import RAGDatabase
# from bishe.generate.llm_generator import create_llm_client, generate_single_message


# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def build_rag_database(force_refresh: bool = False):
    """构建/更新 RAG 向量数据库
    
    Args:
        force_refresh: 是否强制刷新数据库
    """
    from bishe.generate.rag_db import RAGDatabase

    logger.info(f"正在初始化 RAG 数据库并进行向量化存储...{'（强制刷新模式）' if force_refresh else ''}")
    try:
        rag_db = RAGDatabase()
        rag_db.ingest_asn1_blocks(force_refresh=force_refresh)
        logger.info("RAG 数据库更新完成。")
        return True
    except Exception as e:
        logger.error(f"RAG 数据库更新失败: {e}")
        return False


def extract_paths(targets=None):
    """提取 RRC 消息路径
    
    Args:
        targets: 目标类型列表，如果为 None 则默认全部
    """
    from bishe.generate.path_manager import PathManager, TargetType

    logger.info("初始化路径管理器并分析 ASN.1 结构...")
    path_mgr = PathManager()
    
    # 如果没有指定 targets，使用默认值
    if targets is None:
        targets = [TargetType.OCTET_STRING, TargetType.INTEGER, TargetType.BIT_STRING, TargetType.SEQOF]
    
    logger.info(f"目标类型: {[t.name for t in targets]}")
    
    # 提取所有路径
    paths = path_mgr.extract_paths(
        message_name='DL_DCCH_Message',
        targets=targets
    )
    
    if not paths:
        logger.error("未找到任何路径，请检查 RRCLTE_R17 是否正确加载。")
        return False
    
    # 保存路径到文件
    path_mgr.save_paths(paths)
    logger.info(f"路径提取完成。共 {len(paths)} 条。已保存至文件。")
    return True


def generate_messages():
    from bishe.generate.config import Config
    """主逻辑：生成 RRC 消息"""
    from bishe.generate.path_manager import PathManager
    from bishe.generate.rag_db import RAGDatabase
    from bishe.generate.llm_generator import create_llm_client, generate_single_message

    logger.info("开始执行主逻辑：生成 RRC 消息...")
    
    # 1. 读取路径文件
    path_mgr = PathManager()
    paths = path_mgr.load_paths()
    
    if not paths:
        logger.error("未找到路径文件，请先执行 --extract_paths")
        return
    
    logger.info(f"成功加载 {len(paths)} 条路径")
    
    # 2. 初始化 RAG 数据库
    rag_db = RAGDatabase()
    
    # 3. 初始化 LLM（使用 LangChain）
    # TODO: 从配置文件读取 API 密钥和模型设置
    llm = create_llm_client(
        model=Config.OPENAI_MODEL,  # 或从 Config 读取
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY,  # 从环境变量或配置读取
        base_url=Config.OPENAI_BASE_URL
    )
    
    # 4. 遍历每条路径，生成消息
    for idx, path_info in enumerate(paths):
        logger.info(f"\n处理路径 {idx + 1}/{len(paths)}")
        logger.info(f"目标类型: {path_info['target_type']}")
        logger.info(f"路径: {','.join(path_info['path'])}")
        
        # 调用生成函数
        success = generate_single_message(
            llm=llm,
            rag_db=rag_db,
            path_info=path_info,
            max_iterations=20  # 最大迭代次数
        )
        
        if success:
            logger.info(f"路径 {idx + 1} 生成成功")
        else:
            logger.warning(f"路径 {idx + 1} 生成失败")


def main():
    # 必要的延迟导入（枚举类型用于参数定义，必须提前加载）
    # 但为了避免其他重依赖，我们只导入 TargetType
    from bishe.generate.path_manager import TargetType

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="RRC Message Generator with RAG")
    parser.add_argument(
        "-b", "--build_rag", 
        action="store_true", 
        help="构建/更新 RAG 向量数据库"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="强制刷新 RAG 数据库（仅与 -b/--build_rag 一起使用）"
    )
    parser.add_argument(
        "-e", "--extract_paths",
        action="store_true",
        help="提取 RRC 消息路径"
    )
    parser.add_argument(
        "-t", "--targets",
        nargs='*',
        choices=['OCTET_STRING', 'INTEGER', 'BIT_STRING', 'SEQOF'],
        help="指定目标类型（可多选，仅与 -e/--extract_paths 一起使用），默认全部"
    )
    args = parser.parse_args()

    # 检查参数有效性：-f 参数必须与 -b 一起使用
    if args.force and not args.build_rag:
        logger.warning("警告: -f/--force 参数必须与 -b/--build_rag 一起使用，忽略该参数")
        args.force = False
    
    # 检查参数有效性：-t 参数必须与 -e 一起使用
    if args.targets is not None and not args.extract_paths:
        logger.warning("警告: -t/--targets 参数必须与 -e/--extract_paths 一起使用，忽略该参数")
        args.targets = None
    
    # 转换 targets 字符串为 TargetType 枚举
    target_types = None
    if args.targets is not None:
        target_map = {
            'OCTET_STRING': TargetType.OCTET_STRING,
            'INTEGER': TargetType.INTEGER,
            'BIT_STRING': TargetType.BIT_STRING,
            'SEQOF': TargetType.SEQOF
        }
        target_types = [target_map[t] for t in args.targets]
        # 如果指定了 -t 但没有提供值，使用默认值（全部）
        if not target_types:
            target_types = None

    # 如果指定了 --build_rag 参数，执行向量化存储
    if args.build_rag:
        if not build_rag_database(force_refresh=args.force):
            return
    
    # 如果指定了 --extract_paths 参数，提取路径
    if args.extract_paths:
        if not extract_paths(targets=target_types):
            return
    
    # 如果没有指定任何参数，执行主逻辑
    if not args.build_rag and not args.extract_paths:
        generate_messages()


if __name__ == "__main__":
    main()
