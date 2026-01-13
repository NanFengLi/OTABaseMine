import sys
import os
import logging
import argparse

# Add project root to sys path
# From bishe/generate to OTABase root is ../../
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if project_root not in sys.path:
    sys.path.append(project_root)

# Also ensure rrc can be imported here if main_gen needs it directly, 
# although path_manager handles it too. This is safe redundancy.
artifact_rrc_path = os.path.join(project_root, "artifact/test-case-generator")
if artifact_rrc_path not in sys.path:
    sys.path.append(artifact_rrc_path)

from bishe.generate.path_manager import PathManager, TargetType
from bishe.generate.rag_db import RAGDatabase

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    # # 解析命令行参数
    # parser = argparse.ArgumentParser(description="RRC Path Generator and RAG Manager")
    # parser.add_argument(
    #     "--build_rag", 
    #     action="store_true", 
    #     help="是否构建/更新 RAG 向量数据库 (Whether to vectorize data into DB)"
    # )
    # args = parser.parse_args()

    # # 如果指定了 --build_rag 参数，则执行向量化存储
    # if args.build_rag:
    #     logger.info("Step 0: 正在初始化 RAG 数据库并进行向量化存储...")
    #     try:
    #         rag_db = RAGDatabase()
    #         # 可以传入 force_refresh=True 强制重建，或者保持默认增量更新
    #         rag_db.ingest_asn1_blocks(force_refresh=False)
    #         logger.info("RAG 数据库更新完成。")
    #     except Exception as e:
    #         logger.error(f"RAG 数据库更新失败: {e}")
    #         return

    logger.info("Step 1: 初始化路径管理器并分析 ASN.1 结构...")
    path_mgr = PathManager()
    
    # 提取所有路径 (默认 target: OCTET_STRING, INTEGER, BIT_STRING, SEQOF)
    paths = path_mgr.extract_paths(message_name='DL_DCCH_Message',targets=[TargetType.SEQOF])
    
    if not paths:
        logger.error("未找到任何路径，程序退出。请检查 RRCLTE_R17 是否正确加载。")
        return

    # 保存路径到文件
    path_mgr.save_paths(paths)
    logger.info(f"Step 2: 路径提取完成。共 {len(paths)} 条。已保存至文件。")
    

if __name__ == "__main__":
    main()
