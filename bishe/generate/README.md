# bishe/generate 使用说明（Milvus Standalone + BM25）

本文档包含：

1. 环境准备
2. 常用启动命令
3. RAG 入库/检索流程说明
4. 常见问题排查

---

## 1. 环境准备

建议在项目根目录执行。

### 1.1 激活 Conda 环境

```bash
source /home/lab221/miniconda3/bin/activate bishe
```

### 1.2 安装依赖

```bash
pip install -r bishe/generate/requirements.txt
```

### 1.3 配置 `.env`

在 `bishe/generate/.env` 中至少配置：

```env
# Milvus Standalone 地址
MILVUS_URI=http://127.0.0.1:19530

# 侧车文档目录（可不改）
MILVUS_DOCUMENTS_DIR=/home/lab221/Projects/OTABaseMine/bishe/generate/milvus/documents

# BM25 候选池
BM25_CANDIDATE_POOL=3000

# 可选：启用 rerank
DASHSCOPE_API_KEY=你的key
RERANK_MODEL=qwen3-rerank
```

> 说明：若不填 `MILVUS_URI`，会回退到 Milvus Lite 本地 `.db` 文件模式。

---

## 2. 常用启动命令（最重要）

### 2.1 构建 / 重建 RAG 向量库

在 `bishe/generate` 目录：

```bash
python main_gen.py -b
```

强制重建（推荐在切换配置或更换数据后使用）：

```bash
python main_gen.py -b -f
```

### 2.2 提取路径

```bash
python main_gen.py -e
```

指定目标类型：

```bash
python main_gen.py -e -t OCTET_STRING INTEGER BIT_STRING SEQOF
```

### 2.3 运行主生成流程

```bash
python main_gen.py
```

### 2.4 检索自测脚本（推荐）

项目内已提供：`bishe/generate/test/test_rag_retrieval.py`

示例：

```bash
python bishe/generate/test/test_rag_retrieval.py -q RRCConnectionReconfiguration -q MeasSubframePattern -k 3 --hybrid
```

启用 rerank：

```bash
python bishe/generate/test/test_rag_retrieval.py -q RRCConnectionReconfiguration -k 3 --hybrid --rerank
```

---

## 3. RAG 端到端流程

调用关系：

1. `RAGDatabase.ingest_asn1_blocks()`：构建向量库。
2. `RAGDatabase.query_asn1()`：执行检索。

`query_asn1()` 内部：

- metadata 过滤（`_build_where_filter`）
- 向量召回（`MilvusClient.search`）
- 关键词召回（`MilvusClient.query` + 应用层 BM25）
- RRF 融合（`_rrf_merge`）
- 可选 rerank（`rerank_qwen.py`）
- 解析命中文档并返回 `content_chunk`

---

## 4. 切片结构与存储方式

### 4.1 切片结构

每个切片包含：

- `message_releated`
- `block_file`
- `content_chunk`
- `digested_asn_definitions`

### 4.2 为什么有 `milvus/documents/`

为了避免 Milvus 动态字段长度限制，完整正文 JSON 不直接塞进 Milvus。

当前做法：

- **Milvus 中保存**：`pk`、`doc_uid`、`embedding`、`document_path`、metadata
- **本地侧车文件保存**：完整 JSON 正文（在 `milvus/documents/`）

检索命中后，代码会根据 `document_path` 回读侧车文件，再解析正文。

---

## 5. 检索策略说明

### 5.1 向量检索

- embedding 模型：`all-MiniLM-L6-v2`
- 向量字段：`embedding`
- 相似度：COSINE

### 5.2 关键词检索（BM25）

- 先按 metadata 过滤候选
- 从侧车 JSON 中抽取文本
- 使用 `rank-bm25` 排序
- 若 `rank-bm25` 不可用，回退到子串匹配

### 5.3 融合与重排

- 向量路 + 关键词路通过 RRF 融合
- 可选 Qwen rerank（需要 `DASHSCOPE_API_KEY`）

关键参数（见 `config.py`）：

- `VEC_RECALL_K`
- `KW_RECALL_K`
- `BM25_CANDIDATE_POOL`
- `RRF_K`
- `RERANK_CANDIDATE_CAP`
- `RERANK_MODEL`

---

## 6. 快速验证清单

1. 向量库构建成功：`python main_gen.py -b -f` 无报错
2. 自测检索有结果：`test_rag_retrieval.py` 返回 `RESULT_COUNT > 0`
3. 若启用 rerank：确认 `.env` 已设置 `DASHSCOPE_API_KEY`

---

## 7. 常见问题

### Q1：启动像“卡住”

通常是 embedding 模型首次下载慢（Hugging Face 网络问题）。

### Q2：Milvus 报字段过长

已通过侧车文件方案规避；若出现旧数据问题，执行 `python main_gen.py -b -f` 重建。

### Q3：检索结果为 0

- 检查 `collection_count`
- 检查 `MILVUS_URI` 是否指向你当前使用的 Milvus 实例
- 重新执行 `-b -f` 后再测
