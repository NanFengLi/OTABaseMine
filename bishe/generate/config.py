import os
from pathlib import Path
from dotenv import load_dotenv

# 从 .env 文件加载环境变量
load_dotenv()

# 获取项目根目录（OTABase目录）
# config.py位于 OTABase/bishe/generate/config.py
PROJECT_ROOT = Path(__file__).parent.parent.parent

class Config:
    # 向量数据库配置（Milvus Lite 本地文件；也可通过环境变量改为远程 Milvus URI）
    MILVUS_URI = os.getenv(
        "MILVUS_URI",
        str(PROJECT_ROOT / "bishe/generate/milvus/rrc_asn1.db")
    )
    MILVUS_DOCUMENTS_DIR = os.getenv(
        "MILVUS_DOCUMENTS_DIR",
        str(PROJECT_ROOT / "bishe/generate/milvus/documents")
    )
    # 兼容旧字段名（避免其他代码直接引用时报错）
    CHROMA_PERSIST_DIRECTORY = MILVUS_URI
    # 向量数据库的COLLECTION名称
    COLLECTION_NAME = "rrc_asn1_definitions"
    
    # ASN.1 源文件配置
    # 假设用户已经将 ASN.1 文件拆分并放入此目录
    ASN1_BLOCKS_DIR = str(PROJECT_ROOT / "bishe/generate/doc_version_control/source_blocks/36331-j00")
    
    # 大语言模型 (LLM) 配置
    # 使用环境变量作为 API 密钥
    OPENAI_MODEL = "gpt-4"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4")

    # DashScope / Qwen rerank（与 OPENAI 密钥独立；未设置则 hybrid 后仅用 RRF 顺序，不调用 rerank）
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    RERANK_MODEL = os.getenv("RERANK_MODEL", "qwen3-rerank")
    # ASN.1 名称检索：偏语义对齐
    RERANK_INSTRUCT = os.getenv(
        "RERANK_INSTRUCT",
        "Retrieve semantically similar text.",
    )
    # 混合检索与 rerank 规模（环境变量可覆盖）
    VEC_RECALL_K = int(os.getenv("VEC_RECALL_K", "24"))
    KW_RECALL_K = int(os.getenv("KW_RECALL_K", "24"))
    BM25_CANDIDATE_POOL = int(os.getenv("BM25_CANDIDATE_POOL", "3000"))
    RRF_K = int(os.getenv("RRF_K", "60"))
    RERANK_CANDIDATE_CAP = int(os.getenv("RERANK_CANDIDATE_CAP", "40"))
    
    # 生成设置
    MAX_RETRIES = 3
    DEFAULT_SEED = 42

    # 配置生成的RRC目标字段的可达路径存储文件(rrc_paths.json文件)所在根目录
    TARGET_PATH_FILE_ROOT = str(PROJECT_ROOT / "bishe/generate/doc_version_control/rrc_paths")
    #RRC 版本配置
    RRC_VERSION = "36331-j00"

    # 数据库连接配置
    DB_HOST = "10.21.143.60"
    DB_PORT = 13306
    DB_NAME = "rrc_testing"
    DB_USER = "rrc_user"
    DB_PASSWORD = "root"
