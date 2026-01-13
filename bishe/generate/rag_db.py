import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("未安装 chromadb。RAG 功能将受限。")

from config import Config

class RAGDatabase:
    """
    RRC协议向量数据库管理类
    逻辑参考 build_vector_db.py 进行重构
    """
    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2") -> None:
        """
        初始化 RAG 数据库
        
        Args:
            embedding_model: sentence-transformers 模型名称，常用选项：
                - "all-MiniLM-L6-v2" (默认，英文，快速)
                - "paraphrase-multilingual-MiniLM-L12-v2" (多语言)
                - "all-mpnet-base-v2" (英文，更准确但更慢)
        """
        if not CHROMA_AVAILABLE:
            self.client = None
            self.collection = None
            return

        # 路径配置
        # 基准目录设为 self.script_dir (即 bishe/generate)
        self.script_dir = Path(__file__).parent
        # mapping.json 文件的路径，加上了版本控制
        self.mapping_file = self.script_dir / "doc_version_control" / "mapping" / Config.RRC_VERSION / "mapping.json" 
        self.asn1_blocks_dir = self.script_dir / "doc_version_control" / "source_blocks" / Config.RRC_VERSION

        self.db_path = Config.CHROMA_PERSIST_DIRECTORY
        self.collection_name = Config.COLLECTION_NAME

        # 协议版本信息
        self.spec_number = Config.RRC_VERSION.split('-')[0]      # 文档协议号
        self.protocol_version = Config.RRC_VERSION.split('-')[1]  # RRC协议版本号

        # 初始化自定义 Embedding 函数
        self.embedding_model = embedding_model
        # 下载的本地模型，从 Hugging Face 下载模型到本地，这里设置模型的名称
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )

        # 初始化 ChromaDB
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # 创建或获取集合，使用自定义 embedding 函数
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"description": "Vector chunks of RRC ASN.1 protocol specifications"}
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

    def extract_asn_definitions(self, content: str) -> str:
        """
        从文件内容中提取 ASN.1 定义的名称。
        
        Args:
            content: 文件内容字符串，比如：
            AdditionalSpectrumEmission ::=		INTEGER (1..32)
            AdditionalSpectrumEmission-v10l0 ::=	INTEGER (33..288)
            AdditionalSpectrumEmission-r18 ::=	INTEGER (1..288)
            
        Returns:
            逗号分隔的 ASN.1 定义名称字符串，如 "AdditionalSpectrumEmission,AdditionalSpectrumEmission-v10l0,AdditionalSpectrumEmission-r18"
        """
        # 匹配 ASN.1 定义: 标识符 ::= 
        # 标识符通常以大写字母开头，可包含字母、数字、连字符
        pattern = r'^\s*([A-Z][A-Za-z0-9-]*)\s*::='
        
        definitions = []
        for line in content.split('\n'):
            match = re.match(pattern, line)
            if match:
                definitions.append(match.group(1))
        # 字符串拼接方法，用于将一个字符串列表（或可迭代对象） 用逗号 , 连接成一个完整的字符串。
        return ','.join(definitions)

    def build_document_chunks(self, message_releated: str, block_files: List[str]) -> List[Dict[str, Any]]:
        """构建文档切片列表"""
        chunks = []
        for block_file in block_files:
            # 构建完整文件路径
            full_path = self.asn1_blocks_dir / block_file
            content = self.read_file_content(str(full_path))
            
            if content:
                chunk = {
                    "message_releated": message_releated.replace('.asn', ''),
                    "block_file": block_file,
                    "content_chunk": content,
                    "digested_asn_definitions": self.extract_asn_definitions(content),
                }
                chunks.append(chunk)
        return chunks

    def build_metadata(self, message_releated: str, block_file: str) -> Dict[str, str]:
        """构建元数据
        元数据: {"title": "文件名","spec_number": "36331", "version": "j00", "message_releated": "CounterCheck.asn"}
        """
        metadata = {
            "block_file": block_file,
            "spec_number": self.spec_number,
            "version": self.protocol_version,
            "message_releated": message_releated,
        }
        return metadata

    def ingest_asn1_blocks(self, force_refresh: bool = False):
        """
        构建向量数据库
        
        关键设计：分离"向量化内容"和"存储内容"
        - embedding_texts: 用于生成向量的文本（决定检索效果）
        - documents: 实际存储的完整内容（检索后返回的数据）
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return

        if force_refresh:
            logging.info(f"删除旧集合 {self.collection_name}...")
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn,
                metadata={"description": "Vector chunks of RRC ASN.1 protocol specifications"}
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
        
        documents_batch = []      # 存储的完整内容（不会被向量化）
        embeddings_batch = []     # 自己生成的向量
        metadatas_batch = []
        ids_batch = []
        # message_releated格式如：“CounterCheck.asn”
        # block_files格式如：“CounterCheck message.txt“
        for idx, (message_releated, block_files) in enumerate(mapping.items(), 1):
            chunks = self.build_document_chunks(message_releated, block_files)
            
            if not chunks:
                continue
            
            for chunk in chunks:
                block_file = chunk["block_file"]
                metadata = self.build_metadata(message_releated, block_file)
                
                # ===== 用于向量化的内容（只用 ASN.1 定义名称） =====
                embedding_text = chunk["digested_asn_definitions"]
                
                # 存储的完整文档内容（JSON格式，包含所有信息）
                # 将chunk转换为JSON字符串存储
                # ensure_ascii=False，允许非 ASCII 字符直接输出（如中文、emoji）。若为 True（默认），中文会变成 \u4e2d\u6587。
                # indent=2，美化格式：每层缩进 2 个空格，使 JSON 易读。若省略，则输出为紧凑单行（适合网络传输，但难读）。
                document_content = json.dumps(chunk, ensure_ascii=False, indent=2)
                
                # 构建唯一 ID,比如: rrc_36331_j00_CounterCheck_DRB-Identity_information_elements
                safe_doc_name = block_file.replace(' ', '_').replace('.txt', '')
                doc_id = f"rrc_{self.spec_number}_{self.protocol_version}_{message_releated.replace('.asn', '')}_{safe_doc_name}"
                
                # 手动生成 embedding（只对 embedding_text 向量化）
                embedding = self.embedding_fn([embedding_text])[0]
                
                # documents 存完整内容，embeddings 存自定义向量
                documents_batch.append(document_content)  # 完整内容
                embeddings_batch.append(embedding)        # 自定义向量
                metadatas_batch.append(metadata)
                ids_batch.append(doc_id)
                success_count += 1
        
        # 批量添加（提供 embeddings 参数，ChromaDB 就不会对 documents 再次向量化）
        if documents_batch:
            batch_size = 50
            for i in range(0, len(documents_batch), batch_size):
                end = min(i + batch_size, len(documents_batch))
                try:
                    self.collection.add(
                        documents=documents_batch[i:end],
                        embeddings=embeddings_batch[i:end],  # 提供自定义向量
                        metadatas=metadatas_batch[i:end],
                        ids=ids_batch[i:end]
                    )
                except Exception as e:
                    logging.error(f"批量添加失败 ({i}-{end}): {e}")

        logging.info(f"向量数据库构建完成！成功添加切片: {success_count}。处理消息数: {total_count}。")

    def query_asn1(
        self, 
        query_texts: List[str], 
        n_results: int = 5,
        spec_number: Optional[str] = None,
        version: Optional[str] = None,
        message_releated: Optional[str] = None
    ) -> List[str]:
        """
        根据查询文本检索相关的 ASN.1 内容。
        
        Args:
            query_texts: 查询文本列表
            n_results: 返回结果数量
            spec_number: 过滤条件 - 协议号（如 "36331"）
            version: 过滤条件 - 版本号（如 "j00"）
            message_releated: 过滤条件 - 关联消息（如 "CounterCheck.asn"）
        
        注意：documents 存储完整 JSON 内容，embeddings 是基于 digested_asn_definitions 生成的向量。
        查询时会对 query_texts 进行向量化，与存储的 embeddings 进行相似度匹配。
        """
        if not CHROMA_AVAILABLE or self.collection is None:
            return []

        # 构建 metadata 过滤条件列表
        conditions = []
        if spec_number:
            conditions.append({"spec_number": spec_number})
        if version:
            conditions.append({"version": version})
        if message_releated:
            # 确保格式一致
            msg = message_releated if message_releated.endswith('.asn') else f"{message_releated}.asn"
            conditions.append({"message_releated": msg})
        
        # 如果没有指定过滤条件，使用当前实例的 spec_number 和 version
        if not conditions:
            conditions = [
                {"spec_number": self.spec_number},
                {"version": self.protocol_version}
            ]
        
        # ChromaDB 多条件需要用 $and 组合
        if len(conditions) == 1:
            where_filter = conditions[0]
        else:
            where_filter = {"$and": conditions}

        results = self.collection.query(
            query_texts=query_texts,
            n_results=n_results,
            where=where_filter,
            include=["documents"]  # documents 现在存的是完整内容
        )
        
        snippets = []
        seen_block_files = set()  # 用于根据 block_file 去重
        # documents 现在存储的是完整 JSON 内容
        if results.get('documents'):
            for doc_list in results['documents']:
                for doc_str in doc_list:
                    try:
                        doc_json = json.loads(doc_str)
                        block_file = doc_json.get("block_file", "")
                        # 根据 block_file 去重
                        if block_file and block_file not in seen_block_files:
                            seen_block_files.add(block_file)
                            if "content_chunk" in doc_json:
                                snippets.append(doc_json["content_chunk"])
                            else:
                                snippets.append(doc_str)
                    except json.JSONDecodeError:
                        snippets.append(doc_str)
        
        return snippets

if __name__ == "__main__":
    # 初始化数据库（模型加载只执行一次）
    print("初始化 RAGDatabase，加载模型中...")
    rag_db = RAGDatabase()
    print(f"初始化完成！数据库中有 {rag_db.collection.count()} 个文档")
    
    print("\n" + "=" * 50)
    print("交互式查询模式")
    print("输入要查询的 ASN.1 定义名称，输入 'q' 或 'quit' 退出")
    print("输入 'rebuild' 重建数据库")
    print("=" * 50)
    
    while True:
        try:
            query = input("\n请输入查询内容: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['q', 'quit', 'exit']:
                print("退出程序")
                break
            
            if query.lower() == 'rebuild':
                print("重建向量数据库...")
                rag_db.ingest_asn1_blocks(force_refresh=True)
                print("重建完成！")
                continue
            
            # 执行查询
            print(f"\n--- 查询: '{query}' ---")
            results = rag_db.query_asn1([query], n_results=3)
            
            if results:
                for i, result in enumerate(results, 1):
                    preview = result[:2000] + "..." if len(result) > 2000 else result
                    print(f"\n结果 {i}:\n{preview}")
            else:
                print("无结果")
                
        except KeyboardInterrupt:
            print("\n退出程序")
            break
        except Exception as e:
            print(f"查询出错: {e}")


