import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("未安装 chromadb。RAG 功能将受限。")

from .config import Config

class RAGDatabase:
    """
    RRC协议向量数据库管理类
    逻辑参考 build_vector_db.py 进行重构
    """
    def __init__(self) -> None:
        if not CHROMA_AVAILABLE:
            self.client = None
            self.collection = None
            return

        # 路径配置
        self.script_dir = Path(__file__).parent
        self.mapping_file = self.script_dir / "mapping" / "mapping.json"
        
        # 由于 mapping.json 中的路径包含 'asn1_blocks/' 前缀，
        # 且 asn1_blocks 目录位于本脚本所在目录 (bishe/generate) 下，
        # 因此基准目录设为 self.script_dir (即 bishe/generate)
        self.asn1_blocks_dir = self.script_dir

        self.db_path = Config.CHROMA_PERSIST_DIRECTORY
        self.collection_name = Config.COLLECTION_NAME

        # 协议版本信息
        self.protocol_version = "j00"  # RRC协议版本号
        self.spec_number = "36331"      # 文档协议号

        # 初始化 ChromaDB
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # 创建或获取集合
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "RRC ASN.1 protocol documentation"}
        )

    def load_mapping(self) -> Dict[str, List[str]]:
        """加载mapping.json文件"""
        if not os.path.exists(self.mapping_file):
            logging.error(f"映射文件不存在: {self.mapping_file}")
            return {}
            
        logging.info(f"正在加载映射文件: {self.mapping_file}")
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            logging.info(f"成功加载 {len(mapping)} 个ASN.1消息映射")
            return mapping
        except Exception as e:
            logging.error(f"加载映射文件失败: {e}")
            return {}

    def read_file_content(self, file_path: str) -> str:
        """读取单个文档文件的内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content.strip()
        except FileNotFoundError:
            logging.warning(f"文件不存在: {file_path}")
            return ""
        except Exception as e:
            logging.warning(f"读取文件失败 {file_path}: {str(e)}")
            return ""

    def build_document_chunks(self, asn_message: str, doc_files: List[str]) -> List[Dict[str, Any]]:
        """构建文档切片列表"""
        chunks = []
        for doc_file in doc_files:
            # 构建完整文件路径
            full_path = self.asn1_blocks_dir / doc_file
            content = self.read_file_content(str(full_path))
            
            if content:
                chunk = {
                    "message": asn_message.replace('.asn', ''),
                    "content_chunk": content,
                    "source_file": doc_file
                }
                chunks.append(chunk)
        return chunks

    def build_metadata(self, asn_message: str, doc_file: str) -> Dict[str, str]:
        """构建元数据"""
        metadata = {
            "title": doc_file,
            "version": self.protocol_version,
            "spec": self.spec_number,
            "message_name": asn_message,
            "source_file": doc_file
        }
        return metadata

    def ingest_asn1_blocks(self, force_refresh: bool = False):
        """
        构建向量数据库
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return

        if force_refresh:
            logging.info(f"删除旧集合 {self.collection_name}...")
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "RRC ASN.1 protocol documentation"}
            )
        
        # 简单检查是否已存在数据 (如果不是强制刷新)
        if self.collection.count() > 0 and not force_refresh:
            logging.info(f"集合 {self.collection_name} 已包含 {self.collection.count()} 个文档。")
            return

        logging.info("开始构建RRC协议向量数据库...")
        
        mapping = self.load_mapping()
        if not mapping:
            return
            
        total_count = len(mapping)
        success_count = 0
        
        documents_batch = []
        metadatas_batch = []
        ids_batch = []
        
        for idx, (asn_message, doc_files) in enumerate(mapping.items(), 1):
            chunks = self.build_document_chunks(asn_message, doc_files)
            
            if not chunks:
                continue
            
            for chunk in chunks:
                doc_file = chunk["source_file"]
                metadata = self.build_metadata(asn_message, doc_file)
                
                # 准备文档内容：转为 JSON 字符串
                # 移除临时的 source_file 字段
                chunk_to_save = {k: v for k, v in chunk.items() if k != "source_file"}
                document_content = json.dumps(chunk_to_save, ensure_ascii=False, indent=2)
                
                # 构建 ID
                # ID需要唯一,组合消息名和文件名
                safe_doc_name = doc_file.replace(' ', '_').replace('.txt', '')
                doc_id = f"rrc_{self.spec_number}_{asn_message.replace('.asn', '')}_{safe_doc_name}"
                
                documents_batch.append(document_content)
                metadatas_batch.append(metadata)
                ids_batch.append(doc_id)
                success_count += 1
        
        # 批量添加
        if documents_batch:
            # 分批提交防止过大
            batch_size = 50
            for i in range(0, len(documents_batch), batch_size):
                end = min(i + batch_size, len(documents_batch))
                try:
                    self.collection.add(
                        documents=documents_batch[i:end],
                        metadatas=metadatas_batch[i:end],
                        ids=ids_batch[i:end]
                    )
                except Exception as e:
                    logging.error(f"批量添加失败 ({i}-{end}): {e}")

        logging.info(f"向量数据库构建完成！成功添加切片: {success_count}。处理消息数: {total_count}。")

    def query_asn1(self, query_texts: List[str], n_results: int = 5) -> List[str]:
        """
        根据查询文本检索相关的 ASN.1 内容。
        注意：因数据库存储内容变为 JSON 格式，此处会解析 JSON 并返回 content_chunk。
        """
        if not CHROMA_AVAILABLE or self.collection is None:
            return []

        results = self.collection.query(
            query_texts=query_texts,
            n_results=n_results
        )
        
        snippets = []
        if results['documents']:
            for doc_list in results['documents']:
                for doc_str in doc_list:
                    try:
                        doc_json = json.loads(doc_str)
                        if "content_chunk" in doc_json:
                            snippets.append(doc_json["content_chunk"])
                        else:
                            snippets.append(doc_str)
                    except json.JSONDecodeError:
                        snippets.append(doc_str)
        
        return list(set(snippets))

    def get_by_name(self, name: str) -> Optional[str]:
        """Retrieve a specific ASN.1 block by message name (using metadata filter)."""
        if not CHROMA_AVAILABLE or self.collection is None:
            return None
        
        # 尝试通过 metadata "message_name" 查找
        # name 可能是 "CounterCheck" 或 "CounterCheck.asn"
        target_name = name if name.endswith('.asn') else f"{name}.asn"
        
        results = self.collection.get(
            where={"message_name": target_name}
        )
        
        if not results['documents']:
             # 尝试不带 .asn
            results = self.collection.get(
                where={"message_name": name}
            )

        if results['documents']:
            # 可能有多个切片，返回最长的一个？或者合并？
            # 暂时拼接所有内容
            contents = []
            for doc_str in results['documents']:
                try:
                    doc_json = json.loads(doc_str)
                    contents.append(doc_json.get("content_chunk", ""))
                except:
                   contents.append(doc_str)
            return "\n\n".join(contents)
                
        return None
