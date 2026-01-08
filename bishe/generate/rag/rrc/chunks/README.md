# RRC协议向量数据库构建工具

## 功能说明

本工具用于根据 `mapping.json` 中的映射关系，将RRC协议的ASN.1消息与对应的文档内容构建为向量数据库，支持语义检索。

## 数据结构

### 文档切片格式
```json
{
  "message": "CounterCheck.asn",
  "content_chunk": "文件对应的内容"
}
```

### 元数据格式
```json
{
  "title": "文件名",
  "version": "j00",
  "spec": "36331",
  "message_name": "CounterCheck.asn",
  "doc_count": "3"
}
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 构建向量数据库

```bash
python build_vector_db.py
```

脚本会自动：
1. 读取 `mapping/mapping.json` 文件
2. 读取 `asn1_blocks/` 目录下的所有文档文件
3. 为每个ASN.1消息构建文档切片
4. 使用ChromaDB存储向量化数据
5. 保存到 `rag/rrc/chunks/vector_db/` 目录

### 2. 查询示例

脚本运行后会自动执行查询示例，也可以在代码中调用：

```python
from build_vector_db import RRCVectorDBBuilder

builder = RRCVectorDBBuilder(
    mapping_file="path/to/mapping.json",
    asn1_blocks_dir="path/to/asn1_blocks",
    db_path="./vector_db"
)

# 查询
builder.query_example("CounterCheck DRB identity", n_results=3)
```

## 输出结果

运行成功后，会在 `vector_db/` 目录下生成向量数据库文件：
- `chroma.sqlite3` - SQLite数据库文件
- `*.parquet` - Parquet格式的向量数据

## 查询结果示例

```
🔍 查询示例: 'CounterCheck DRB identity'
------------------------------------------------------------

结果 1:
  标题: CounterCheck.asn (包含3个文档)
  消息: CounterCheck.asn
  版本: j00
  协议: 36331
  相似度得分: 0.8523
  内容预览: {"message": "CounterCheck.asn", "content_chunk": "=== CounterCheck message.txt ===\n..."}...
```

## 技术栈

- **ChromaDB**: 开源向量数据库
- **Sentence Transformers**: 文本向量化模型
- **Python 3.8+**: 脚本运行环境

## 注意事项

1. 首次运行时会自动下载embedding模型（约400MB），需要网络连接
2. 向量数据库大小取决于文档数量，预计约几百MB
3. 查询速度与文档数量和硬件配置相关

## 高级配置

### 自定义Embedding模型

在 `build_vector_db.py` 中可以修改：

```python
# 使用OpenAI的embedding
from chromadb.utils import embedding_functions
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key="your-api-key",
    model_name="text-embedding-ada-002"
)

# 创建集合时指定
self.collection = self.client.get_or_create_collection(
    name=collection_name,
    embedding_function=openai_ef
)
```

### 自定义协议版本

修改初始化参数：

```python
builder = RRCVectorDBBuilder(
    mapping_file=str(mapping_file),
    asn1_blocks_dir=str(asn1_blocks_dir),
    db_path=str(vector_db_path),
    collection_name="rrc_asn1_docs"
)

# 修改协议版本
builder.protocol_version = "your-version"
builder.spec_number = "your-spec-number"
```

## 故障排除

### 问题1: 找不到文件
- 检查 `mapping.json` 路径是否正确
- 确认 `asn1_blocks/` 目录存在且包含文档文件

### 问题2: 内存不足
- 减少批处理大小
- 使用更轻量级的embedding模型

### 问题3: ChromaDB错误
- 删除 `vector_db/` 目录重新构建
- 更新ChromaDB到最新版本

## 许可证

本工具仅用于学习和研究目的。
