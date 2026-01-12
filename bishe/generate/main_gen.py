import sys
import os
import logging

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
    paths = path_mgr.extract_paths(message_name='DL_DCCH_Message',targets=[TargetType.OCTET_STRING])
    
    if not paths:
        logger.error("未找到任何路径，程序退出。请检查 RRCLTE_R17 是否正确加载。")
        return

    # 保存路径到文件
    path_mgr.save_paths(paths)
    logger.info(f"Step 2: 路径提取完成。共 {len(paths)} 条。已保存至文件。")
    

if __name__ == "__main__":
    main()
