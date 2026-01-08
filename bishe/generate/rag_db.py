import os
import glob
import logging
from typing import List, Optional

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("未安装 chromadb。RAG 功能将受限。")

from .config import Config

class RAGDatabase:
    def __init__(self):
        if not CHROMA_AVAILABLE:
            self.client = None
            self.collection = None
            return

        self.client = chromadb.PersistentClient(path=Config.CHROMA_PERSIST_DIRECTORY)
        # 暂时使用默认的嵌入函数，后续可以替换为 OpenAI 或其他模型
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        self.collection = self.client.get_or_create_collection(
            name=Config.COLLECTION_NAME,
            embedding_function=self.embedding_fn
        )

    def ingest_asn1_blocks(self, force_refresh: bool = False):
        """
        从配置的目录读取 ASN.1 文件并将其添加到向量数据库中。
        每个文件被视为一个文档。
        """
        if not CHROMA_AVAILABLE:
            return

        if force_refresh:
            self.client.delete_collection(Config.COLLECTION_NAME)
            self.collection = self.client.get_or_create_collection(
                name=Config.COLLECTION_NAME,
                embedding_function=self.embedding_fn
            )

        # 检查是否已经填充（简单检查）
        if self.collection.count() > 0 and not force_refresh:
            logging.info(f"集合 {Config.COLLECTION_NAME} 已包含 {self.collection.count()} 个文档。")
            return

        asn_files = glob.glob(os.path.join(Config.ASN1_BLOCKS_DIR, "*.asn"))
        if not asn_files:
            logging.warning(f"在 {Config.ASN1_BLOCKS_DIR} 中未找到 ASN.1 文件")
            return

        documents = []
        metadatas = []
        ids = []

        for filepath in asn_files:
            filename = os.path.basename(filepath)
            # 假设：文件名是消息名称或主要 IE 名称，例如 "DL-DCCH-Message.asn"
            obj_name = os.path.splitext(filename)[0]
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            documents.append(content)
            metadatas.append({"source": filename, "name": obj_name})
            ids.append(obj_name)

        if documents:
            # 如果需要，可以批量添加，目前为简单起见一次性添加
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logging.info(f"已摄入 {len(documents)} 个 ASN.1 块。")

    def query_asn1(self, query_texts: List[str], n_results: int = 5) -> List[str]:
        """
        根据查询文本（例如消息名称或字段路径）检索相关的 ASN.1 片段。
        """
        if not CHROMA_AVAILABLE or self.collection is None:
            return []

        results = self.collection.query(
            query_texts=query_texts,
            n_results=n_results
        )
        
        # 展平结果
        snippets = []
        if results['documents']:
            for doc_list in results['documents']:
                snippets.extend(doc_list)
        
        return list(set(snippets)) # 去重

    def get_by_name(self, name: str) -> Optional[str]:
        """Retrieve a specific ASN.1 block by exact name match (ID)."""
        if not CHROMA_AVAILABLE or self.collection is None:
            return None
        
        result = self.collection.get(ids=[name])
        if result['documents']:
            return result['documents'][0]
        return None
