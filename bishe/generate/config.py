import os
from dotenv import load_dotenv

# 从 .env 文件加载环境变量
load_dotenv()

class Config:
    # 向量数据库配置
    CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_DB_DIR", "./chroma_db")
    COLLECTION_NAME = "rrc_asn1_definitions"
    
    # ASN.1 源文件配置
    # 假设用户已经将 ASN.1 文件拆分并放入此目录
    ASN1_BLOCKS_DIR = os.getenv("ASN1_BLOCKS_DIR", "../asn1_blocks")
    
    # 大语言模型 (LLM) 配置
    # 使用环境变量作为 API 密钥
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    
    # 生成设置
    MAX_RETRIES = 3
    DEFAULT_SEED = 42

    # 路径引导配置
    PATH_DB_FILE = os.getenv("PATH_DB_FILE", "./rrc_paths.json")
