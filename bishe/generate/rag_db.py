import os
import re
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    from pymilvus import MilvusClient
    from sentence_transformers import SentenceTransformer
    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False
    logging.warning("未安装 pymilvus/sentence-transformers。RAG 功能将受限。")

try:
    import importlib
    BM25Okapi = importlib.import_module("rank_bm25").BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logging.warning("未安装 rank-bm25。关键词检索将回退为子串匹配。")

try:
    from bishe.generate.config import Config
except ImportError:
    from config import Config

try:
    from bishe.generate.rerank_qwen import rerank_document_indices
except ImportError:
    from rerank_qwen import rerank_document_indices


class RAGDatabase:
    """
    RRC协议向量数据库管理类
    逻辑参考 build_vector_db.py 进行重构
    """
    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2") -> None:
        """
        初始化 RAG 数据库（Milvus 版本）。
        """
        if not MILVUS_AVAILABLE:
            self.client = None
            self.collection = None
            return

        self.script_dir = Path(__file__).parent
        self.mapping_file = self.script_dir / "doc_version_control" / "mapping" / Config.RRC_VERSION / "mapping.json"
        self.asn1_blocks_dir = self.script_dir / "doc_version_control" / "source_blocks" / Config.RRC_VERSION

        self.db_uri = Config.MILVUS_URI
        self.collection_name = Config.COLLECTION_NAME
        self.documents_dir = Path(Config.MILVUS_DOCUMENTS_DIR)
        self.documents_dir.mkdir(parents=True, exist_ok=True)

        self.spec_number = Config.RRC_VERSION.split('-')[0]
        self.protocol_version = Config.RRC_VERSION.split('-')[1]

        self.embedding_model = embedding_model
        self.embedding_fn = SentenceTransformer(embedding_model)
        self.embedding_dim = int(self.embedding_fn.get_sentence_embedding_dimension())

        # Milvus Lite 本地文件模式
        if self.db_uri.endswith(".db"):
            Path(self.db_uri).parent.mkdir(parents=True, exist_ok=True)

        self.client = MilvusClient(uri=self.db_uri)
        self._ensure_collection()
        # 兼容旧代码中对 self.collection 的空值判断
        self.collection = self.collection_name

    def _ensure_collection(self) -> None:
        if self.client.has_collection(collection_name=self.collection_name):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            dimension=self.embedding_dim,
            metric_type="COSINE",
            auto_id=False,
            primary_field_name="pk",
            id_type="int",
            vector_field_name="embedding",
            enable_dynamic_field=True,
        )

    def _drop_and_recreate_collection(self) -> None:
        if self.client.has_collection(collection_name=self.collection_name):
            self.client.drop_collection(collection_name=self.collection_name)
        self._ensure_collection()

    def _collection_count(self) -> int:
        if not self.client:
            return 0
        try:
            stats = self.client.get_collection_stats(collection_name=self.collection_name)
            return int(stats.get("row_count", 0))
        except Exception:
            return 0

    @staticmethod
    def _stable_int64(text: str) -> int:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        return int(digest, 16) & 0x7FFFFFFFFFFFFFFF

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
        - document: 实际存储的完整内容（检索后返回的数据）
        """
        if not MILVUS_AVAILABLE or not self.client:
            return

        if force_refresh:
            logging.info(f"删除旧集合 {self.collection_name}...")
            self._drop_and_recreate_collection()
        
        # 简单检查是否已存在数据 (如果不是强制刷新)
        current_count = self._collection_count()
        if current_count > 0 and not force_refresh:
            logging.info(f"集合 {self.collection_name} 已包含 {current_count} 个文档。")
            return

        logging.info("开始构建 RRC 协议向量数据库（Milvus）...")
        
        mapping = self.load_mapping()
        if not mapping:
            return
            
        total_count = len(mapping)
        success_count = 0
        
        rows_batch: List[Dict[str, Any]] = []
        # message_releated格式如：“CounterCheck.asn”
        # block_files格式如：“CounterCheck message.txt“
        for message_releated, block_files in mapping.items():
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
                
                if not embedding_text:
                    continue

                document_path = self.documents_dir / f"{doc_id}.json"
                try:
                    with open(document_path, "w", encoding="utf-8") as f:
                        f.write(document_content)
                except Exception as e:
                    logging.error(f"写入文档侧车文件失败 {document_path}: {e}")
                    continue

                embedding = (
                    self.embedding_fn.encode([embedding_text], normalize_embeddings=True)[0]
                    .astype("float32")
                    .tolist()
                )

                rows_batch.append(
                    {
                        "pk": self._stable_int64(doc_id),
                        "doc_uid": doc_id,
                        "embedding": embedding,
                        "document_path": str(document_path),
                        "block_file": metadata["block_file"],
                        "spec_number": metadata["spec_number"],
                        "version": metadata["version"],
                        "message_releated": metadata["message_releated"],
                    }
                )
                success_count += 1
        
        if rows_batch:
            batch_size = 50
            for i in range(0, len(rows_batch), batch_size):
                end = min(i + batch_size, len(rows_batch))
                try:
                    self.client.insert(
                        collection_name=self.collection_name,
                        data=rows_batch[i:end],
                    )
                except Exception as e:
                    logging.error(f"批量添加失败 ({i}-{end}): {e}")

        logging.info(f"向量数据库构建完成！成功添加切片: {success_count}。处理消息数: {total_count}。")

    def _build_where_filter(
        self,
        spec_number: Optional[str],
        version: Optional[str],
        message_releated: Optional[str],
    ) -> str:
        conditions: List[str] = []
        if spec_number:
            conditions.append(f'spec_number == "{spec_number}"')
        if version:
            conditions.append(f'version == "{version}"')
        if message_releated:
            msg = message_releated if message_releated.endswith(".asn") else f"{message_releated}.asn"
            conditions.append(f'message_releated == "{msg}"')

        if not conditions:
            conditions = [
                f'spec_number == "{self.spec_number}"',
                f'version == "{self.protocol_version}"',
            ]
        return " and ".join(conditions)

    @staticmethod
    def _parse_stored_document(doc_str: str) -> Tuple[str, str]:
        """从存储的 JSON 文档解析 (block_file, 用于展示的正文)."""
        try:
            doc_json = json.loads(doc_str)
            block_file = doc_json.get("block_file", "") or ""
            if "content_chunk" in doc_json:
                return block_file, doc_json["content_chunk"]
            return block_file, doc_str
        except json.JSONDecodeError:
            return "", doc_str

    @staticmethod
    def _extract_doc_from_hit(hit: Dict[str, Any]) -> Tuple[str, str]:
        """从 Milvus 查询/搜索结果中提取 (doc_uid, document)。"""
        if not isinstance(hit, dict):
            return "", ""

        entity = hit.get("entity") if isinstance(hit.get("entity"), dict) else {}
        doc_uid = (
            hit.get("doc_uid")
            or entity.get("doc_uid")
            or str(hit.get("id") or "")
        )
        document = hit.get("document") or entity.get("document") or ""
        if not document:
            document_path = hit.get("document_path") or entity.get("document_path") or ""
            if document_path:
                document = str(document_path)
        return str(doc_uid), str(document)

    def _load_document_from_ref(self, doc_ref: str) -> str:
        """根据本地侧车文件路径或内联 JSON 字符串加载完整文档。"""
        if not doc_ref:
            return ""
        path = Path(doc_ref)
        if path.exists() and path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                logging.debug("读取文档侧车文件失败 %s: %s", path, e)
                return ""
        return doc_ref

    @staticmethod
    def _extract_text_for_keyword(doc_str: str) -> str:
        """从 document(JSON 字符串)中抽取用于 BM25 的文本。"""
        if not doc_str:
            return ""
        try:
            data = json.loads(doc_str)
            parts = [
                str(data.get("digested_asn_definitions", "") or ""),
                str(data.get("content_chunk", "") or ""),
                str(data.get("block_file", "") or ""),
                str(data.get("message_releated", "") or ""),
            ]
            return "\n".join([p for p in parts if p])
        except Exception:
            return doc_str

    @staticmethod
    def _tokenize_for_bm25(text: str) -> List[str]:
        """ASN.1 友好分词：保留字母/数字/连字符，统一小写。"""
        if not text:
            return []
        return [t for t in re.findall(r"[A-Za-z0-9-]+", text.lower()) if len(t) >= 2]

    @staticmethod
    def _rrf_merge(rank_lists: List[List[str]], k: int) -> List[str]:
        """倒数排名融合：多路有序 id 列表合并为单一排序。"""
        scores: Dict[str, float] = {}
        for ranks in rank_lists:
            if not ranks:
                continue
            for i, doc_id in enumerate(ranks):
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + i + 1)
        return sorted(scores.keys(), key=lambda x: -scores[x])

    def _keyword_candidates(
        self, query_text: str, where_filter: str, limit: int
    ) -> Tuple[List[str], Dict[str, str]]:
        """
        关键词召回：先按 metadata 过滤查询，再在 document 文本上做 BM25 排序。
        若未安装 rank-bm25，则回退为子串匹配排序。
        返回 (有序 id 列表, id -> document 字符串)。
        """
        q = query_text.strip()
        if not q:
            return [], {}
        try:
            candidate_pool = max(Config.BM25_CANDIDATE_POOL, limit * 10)
            candidate_pool = min(candidate_pool, 16384)

            candidates = self.client.query(
                collection_name=self.collection_name,
                filter=where_filter,
                output_fields=["doc_uid", "document_path"],
                limit=candidate_pool,
            )

            docs: List[Tuple[str, str, str]] = []
            for item in candidates or []:
                doc_uid, doc = self._extract_doc_from_hit(item)
                if not doc_uid or not doc:
                    continue
                full_doc = self._load_document_from_ref(doc)
                docs.append((doc_uid, full_doc, self._extract_text_for_keyword(full_doc)))

            if not docs:
                return [], {}

            scored_ids: List[str] = []
            if BM25_AVAILABLE:
                tokenized_corpus = [self._tokenize_for_bm25(t) for _, _, t in docs]
                query_tokens = self._tokenize_for_bm25(q)
                if query_tokens and any(tokenized_corpus):
                    bm25 = BM25Okapi(tokenized_corpus)
                    scores = bm25.get_scores(query_tokens)
                    order = sorted(
                        range(len(docs)),
                        key=lambda i: float(scores[i]),
                        reverse=True,
                    )
                    scored_ids = [docs[i][0] for i in order if float(scores[i]) > 0.0]

            if not scored_ids:
                q_low = q.lower()
                fallback_scored: List[Tuple[Tuple[int, int], str]] = []
                for doc_uid, _, text in docs:
                    low = text.lower()
                    if q_low in low:
                        fallback_scored.append(((-low.count(q_low), low.find(q_low)), doc_uid))
                fallback_scored.sort(key=lambda x: x[0])
                scored_ids = [doc_id for _, doc_id in fallback_scored]

            id_to_doc: Dict[str, str] = {}
            ids: List[str] = []
            doc_lookup = {doc_uid: doc for doc_uid, doc, _ in docs}
            for doc_id in scored_ids[:limit]:
                doc = doc_lookup.get(doc_id)
                if doc is None:
                    continue
                ids.append(doc_id)
                id_to_doc[doc_id] = doc
            return ids, id_to_doc
        except Exception as e:
            logging.debug("关键词召回失败（可忽略并仅使用向量）: %s", e)
            return [], {}

    def _hybrid_ranked_chunks(
        self,
        query_text: str,
        where_filter: str,
        n_results: int,
        hybrid: bool,
        use_rerank: bool,
    ) -> List[Tuple[str, str]]:
        """
        单条查询：向量 + 关键词（可选）融合后，可选 qwen rerank，返回 [(block_file, content_chunk), ...]。
        """
        vec_k = max(n_results, Config.VEC_RECALL_K)
        kw_k = max(n_results, Config.KW_RECALL_K)
        cap = max(n_results, min(Config.RERANK_CANDIDATE_CAP, vec_k + kw_k))

        if not self.client:
            return []

        query_vec = (
            self.embedding_fn.encode([query_text], normalize_embeddings=True)[0]
            .astype("float32")
            .tolist()
        )

        vec_results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vec],
            anns_field="embedding",
            filter=where_filter,
            limit=vec_k,
            output_fields=["doc_uid", "document_path", "block_file"],
            search_params={"metric_type": "COSINE", "params": {}},
        )

        vec_ids: List[str] = []
        id_to_doc: Dict[str, str] = {}
        first_hits = vec_results[0] if vec_results else []
        for hit in first_hits:
            doc_uid, doc = self._extract_doc_from_hit(hit)
            if not doc_uid or not doc:
                continue
            if doc_uid not in id_to_doc:
                vec_ids.append(doc_uid)
                id_to_doc[doc_uid] = self._load_document_from_ref(doc)

        kw_ids: List[str] = []
        if hybrid:
            kw_ids, kw_id_to_doc = self._keyword_candidates(query_text, where_filter, kw_k)
            id_to_doc.update(kw_id_to_doc)

        rank_lists = [vec_ids]
        if hybrid and kw_ids:
            rank_lists.append(kw_ids)
        merged_ids = self._rrf_merge(rank_lists, k=Config.RRF_K)

        # 按融合顺序收集 (block_file, content)，去重 block_file，长度受 cap 限制
        ordered: List[Tuple[str, str]] = []
        seen_bf: set = set()
        for doc_id in merged_ids:
            if doc_id not in id_to_doc:
                continue
            bf, content = self._parse_stored_document(id_to_doc[doc_id])
            if bf and bf in seen_bf:
                continue
            if bf:
                seen_bf.add(bf)
            ordered.append((bf, content))
            if len(ordered) >= cap:
                break

        if not ordered:
            return []

        if use_rerank and Config.DASHSCOPE_API_KEY:
            texts = [t[1] for t in ordered]
            rerank_top = min(len(texts), max(n_results, cap))
            new_idx = rerank_document_indices(
                query_text,
                texts,
                top_n=rerank_top,
            )
            if new_idx is not None:
                reranked: List[Tuple[str, str]] = []
                seen2: set = set()
                for i in new_idx:
                    if 0 <= i < len(ordered):
                        bf, content = ordered[i]
                        if bf and bf in seen2:
                            continue
                        if bf:
                            seen2.add(bf)
                        reranked.append((bf, content))
                        if len(reranked) >= n_results:
                            break
                if reranked:
                    return reranked

        return ordered[:n_results]

    def query_asn1(
        self,
        query_texts: List[str],
        n_results: int = 5,
        spec_number: Optional[str] = None,
        version: Optional[str] = None,
        message_releated: Optional[str] = None,
        hybrid: bool = True,
        use_rerank: bool = True,
    ) -> List[str]:
        """
        根据查询文本检索相关的 ASN.1 内容。

        默认：Milvus 向量召回 + 应用层关键词子串召回，RRF 融合后使用 qwen3-rerank（DashScope）重排。

        Args:
            query_texts: 查询文本列表
            n_results: 每个查询返回的条数（合并去重前按查询依次截取）
            spec_number / version / message_releated: metadata 过滤
            hybrid: 是否启用关键词分支（False 时仅向量 + 可选 rerank）
            use_rerank: 是否在融合后调用 rerank（仍需要配置 DASHSCOPE_API_KEY）

        注意：embeddings 基于 digested_asn_definitions；关键词匹配落在完整 JSON 文本上，可命中 content_chunk 中的类型名。
        """
        if not MILVUS_AVAILABLE or not self.client:
            return []

        where_filter = self._build_where_filter(spec_number, version, message_releated)

        snippets: List[str] = []
        seen_block_files: set = set()

        for qt in query_texts:
            ranked = self._hybrid_ranked_chunks(
                qt, where_filter, n_results, hybrid=hybrid, use_rerank=use_rerank
            )
            for block_file, content in ranked:
                if block_file and block_file not in seen_block_files:
                    seen_block_files.add(block_file)
                    snippets.append(content)
                elif not block_file:
                    snippets.append(content)

        return snippets

if __name__ == "__main__":
    # 初始化数据库（模型加载只执行一次）
    print("初始化 RAGDatabase，加载模型中...")
    rag_db = RAGDatabase()
    
    doc_count = rag_db._collection_count() if rag_db.client else 0
    
    print(f"初始化完成！数据库中有 {doc_count} 个文档")
    
    if doc_count == 0:
        print("\n" + "!" * 50)
        print(" [提示] 数据库当前为空，无法检索到任何内容。")
        print(" -> 请输入 'rebuild' 并回车，程序将开始读取本地文件并构建向量库。")
        print("!" * 50)
    
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


