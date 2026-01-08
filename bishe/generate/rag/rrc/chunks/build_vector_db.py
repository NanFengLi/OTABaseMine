#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RRC协议ASN.1文件向量数据库构建脚本

功能说明：
1. 读取mapping.json文件，获取ASN.1消息与对应文档文件的映射关系
2. 读取每个文档文件的内容
3. 将ASN.1消息名称和对应文档内容构建为向量数据库的文档切片
4. 使用向量嵌入技术存储到向量数据库中，便于后续语义检索

数据格式：
- 文档切片: {"message": "CounterCheck", "content_chunk": "文件内容"}
- 元数据: {"title": "文件名", "version": "j00", "spec": "36331"}
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings


class RRCVectorDBBuilder:
    """RRC协议向量数据库构建器"""
    
    def __init__(
        self, 
        mapping_file: str,
        asn1_blocks_dir: str,
        db_path: str = "./vector_db",
        collection_name: str = "rrc_asn1_docs"
    ):
        """
        初始化向量数据库构建器
        
        Args:
            mapping_file: mapping.json文件路径
            asn1_blocks_dir: asn1_blocks文件夹路径
            db_path: 向量数据库存储路径
            collection_name: 集合名称
        """
        self.mapping_file = mapping_file
        self.asn1_blocks_dir = asn1_blocks_dir
        self.db_path = db_path
        self.collection_name = collection_name
        
        # 协议版本信息
        self.protocol_version = "j00"  # RRC协议版本号
        self.spec_number = "36331"      # 文档协议号
        
        # 初始化ChromaDB客户端 (适配 v0.4.0+)
        # 使用 PersistentClient 直接指定持久化路径，无需配置 duckdb+parquet
        self.client = chromadb.PersistentClient(path=db_path)
        
        # 创建或获取集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "RRC ASN.1 protocol documentation"}
        )
    
    def load_mapping(self) -> Dict[str, List[str]]:
        """
        加载mapping.json文件
        
        Returns:
            字典，键为ASN.1文件名，值为对应的文档文件列表
        """
        print(f"正在加载映射文件: {self.mapping_file}")
        
        with open(self.mapping_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        # 这段代码会输出 JSON 文件中顶层键（Key）的数量。
        print(f"成功加载 {len(mapping)} 个ASN.1消息映射")
        return mapping
    
    def read_file_content(self, file_path: str) -> str:
        """
        读取单个文档文件的内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容字符串
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 删除首尾空白字符（包括空行）
            return content.strip()
        except FileNotFoundError:
            print(f"文件不存在: {file_path}")
            return ""
        except Exception as e:
            print(f"读取文件失败 {file_path}: {str(e)}")
            return ""
    
    def build_document_chunks(
        self, 
        asn_message: str, 
        doc_files: List[str]
    ) -> List[Dict[str, Any]]:
        """
        构建文档切片列表（每个文件一个切片）
        
        Args:
            asn_message: ASN.1消息名称（如 "CounterCheck.asn"）
            doc_files: 对应的文档文件列表
            
        Returns:
            包含多个切片的列表
        """
        chunks = []
        for doc_file in doc_files:
            # 构建完整文件路径
            full_path = os.path.join(self.asn1_blocks_dir, doc_file)
            content = self.read_file_content(full_path)
            
            if content:
                # 构建单个文档切片
                chunk = {
                    "message": asn_message.replace('.asn', ''),
                    "content_chunk": content,  # 直接使用文件内容，不添加分隔符
                    "source_file": doc_file    # 记录具体来源文件
                }
                chunks.append(chunk)
        
        return chunks
    
    def build_metadata(self, asn_message: str, doc_file: str) -> Dict[str, str]:
        """
        构建元数据
        
        Args:
            asn_message: ASN.1消息名称
            doc_file: 当前文档文件名
            
        Returns:
            元数据字典
        """
        metadata = {
            "title": doc_file,  # 标题直接使用当前文件名
            "version": self.protocol_version,
            "spec": self.spec_number,
            "message_name": asn_message,
            "source_file": doc_file
        }
        
        return metadata
    
    def add_to_vector_db(
        self, 
        document: str, 
        metadata: Dict[str, str], 
        doc_id: str
    ):
        """
        将文档添加到向量数据库
        
        Args:
            document: 文档内容
            metadata: 元数据
            doc_id: 文档唯一ID
        """
        self.collection.add(
            documents=[document],
            metadatas=[metadata],
            ids=[doc_id]
        )
    
    def build(self):
        """
        执行完整的向量数据库构建流程
        """
        print("\n" + "="*60)
        print("开始构建RRC协议向量数据库")
        print("="*60 + "\n")
        
        # 1. 加载映射关系
        mapping = self.load_mapping()
        
        # 2. 遍历每个ASN.1消息
        total_count = len(mapping)
        success_count = 0
        
        for idx, (asn_message, doc_files) in enumerate(mapping.items(), 1):
            print(f"\n[{idx}/{total_count}] 处理: {asn_message}")
            print(f"关联文档数: {len(doc_files)}")
            
            # 3. 构建文档切片列表
            chunks = self.build_document_chunks(asn_message, doc_files)
            
            if not chunks:
                print(f"跳过（无有效内容）")
                continue
            
            # 遍历每个切片并添加到数据库
            for chunk in chunks:
                doc_file = chunk["source_file"]
                
                # 4. 构建元数据
                metadata = self.build_metadata(asn_message, doc_file)
                
                # 5. 准备文档内容（将chunk转为JSON字符串）
                # 移除临时的 source_file 字段，保持数据整洁
                chunk_to_save = {k: v for k, v in chunk.items() if k != "source_file"}
                document_content = json.dumps(chunk_to_save, ensure_ascii=False, indent=2)
                
                # 6. 添加到向量数据库
                # ID需要唯一，组合消息名和文件名
                safe_doc_name = doc_file.replace(' ', '_').replace('.txt', '')
                doc_id = f"rrc_{self.spec_number}_{asn_message.replace('.asn', '')}_{safe_doc_name}"
                
                try:
                    self.add_to_vector_db(document_content, metadata, doc_id)
                    success_count += 1
                    # print(f"添加切片: {doc_file}")
                except Exception as e:
                    print(f"添加失败 {doc_file}: {str(e)}")
            
            print(f"已处理 {len(chunks)} 个切片")
        
        # 7. 持久化数据库 (v0.4.0+ 自动持久化，无需手动调用 persist)
        # self.client.persist()
        
        print("\n" + "="*60)
        print(f"向量数据库构建完成！")
        print(f"统计信息:")
        print(f"   - 总消息数: {total_count}")
        print(f"   - 成功添加: {success_count}")
        print(f"   - 跳过: {total_count - success_count}")
        print(f"   - 数据库路径: {self.db_path}")
        print(f"   - 集合名称: {self.collection_name}")
        print("="*60 + "\n")
    
    def query_example(self, query_text: str, n_results: int = 3):
        """
        查询示例 - 展示如何使用构建好的向量数据库
        
        Args:
            query_text: 查询文本
            n_results: 返回结果数量
        """
        print(f"\n查询示例: '{query_text}'")
        print("-" * 60)
        
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        
        for idx, (doc, metadata, distance) in enumerate(
            zip(results['documents'][0], results['metadatas'][0], results['distances'][0]), 
            1
        ):
            print(f"\n结果 {idx}:")
            print(f"  标题: {metadata.get('title')}")
            print(f"  消息: {metadata.get('message_name')}")
            print(f"  版本: {metadata.get('version')}")
            print(f"  协议: {metadata.get('spec')}")
            print(f"  相似度得分: {1 - distance:.4f}")
            print(f"  内容预览: {doc[:200]}...")


def main():
    """主函数"""
    # 获取项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent.parent
    
    # 设置路径
    mapping_file = project_root / "mapping" / "mapping.json"
    # mapping.json 中的路径已包含 asn1_blocks/ 前缀，因此基准目录设为项目根目录
    asn1_blocks_dir = project_root
    vector_db_path = script_dir / "vector_db"
    
    print(f"项目根目录: {project_root}")
    print(f"映射文件: {mapping_file}")
    print(f"文档目录: {asn1_blocks_dir}")
    print(f"数据库路径: {vector_db_path}")
    
    # 检查必要的文件和目录
    if not mapping_file.exists():
        print(f"错误: 映射文件不存在: {mapping_file}")
        return
    
    if not asn1_blocks_dir.exists():
        print(f"错误: 文档目录不存在: {asn1_blocks_dir}")
        return
    
    # 创建向量数据库构建器
    builder = RRCVectorDBBuilder(
        mapping_file=str(mapping_file),
        asn1_blocks_dir=str(asn1_blocks_dir),
        db_path=str(vector_db_path),
        collection_name="rrc_asn1_docs"
    )
    
    # 构建向量数据库
    builder.build()
    
    # 运行查询示例
    print("\n" + "="*60)
    print("运行查询示例")
    print("="*60)
    builder.query_example("CounterCheck DRB identity", n_results=3)
    builder.query_example("RRC connection reconfiguration", n_results=3)


if __name__ == "__main__":
    main()
