import sys
import os
import logging
import random

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
from bishe.generate.rrc_rag_generator import RRCGeneratorRAG

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Step 1: 初始化路径管理器并分析 ASN.1 结构...")
    path_mgr = PathManager()
    
    # 提取所有路径 (默认 target: OCTET_STRING, INTEGER, BIT_STRING, SEQOF)
    paths = path_mgr.extract_paths(message_name='DL-DCCH-Message',targets=[TargetType.OCTET_STRING])
    
    if not paths:
        logger.error("未找到任何路径，程序退出。请检查 RRCLTE_R17 是否正确加载。")
        return

    # 保存路径到文件
    path_mgr.save_paths(paths)
    logger.info(f"Step 2: 路径提取完成。共 {len(paths)} 条。已保存至文件。")

    # ---------------------------------------------------------
    # 演示：随机选取一条路径，并使用 RAG + LLM 生成代码
    # ---------------------------------------------------------
    
    # 随机选一条
    # selected = random.choice(paths)
    # target_path = selected['path']
    # choices = selected['choices']
    
    # logger.info("-" * 50)
    # logger.info(f"演示生成流程")
    # logger.info(f"选中路径: {target_path}")
    # logger.info(f"决策序列: {choices}")
    
    # logger.info("Step 3: 初始化 RAG 生成器 (可能会加载向量数据库)...")
    # generator = RRCGeneratorRAG(load_db=True)
    
    # msg_type = "DL-DCCH-Message"
    
    # 为了让 LLM 更好地工作，我们将 choice 序列也整合到 path 信息中，或者仅提供 path
    # 这里我们提供 path，RAG 会检索相关字段定义
    
    # logger.info(f"Step 4: 请求 LLM 生成代码...")
    # generated_structure = generator.generate(msg_type, target_path)
    
    # logger.info("生成结果:")
    # print(generated_structure)

if __name__ == "__main__":
    main()
