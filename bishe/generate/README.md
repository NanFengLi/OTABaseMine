# bishe/generate — RAG 与检索说明

本文说明当前工程里 **ChromaDB 检索如何工作**，以及 **「关键词检索」**的真实含义（与 BM25 的区别）。

---

## 一、入库时 Chroma 里存了什么

每条记录包含三部分（见 `rag_db.py` 的 `ingest_asn1_blocks`）：

| 字段 | 内容 |
|------|------|
| **embeddings** | 仅对 `digested_asn_definitions`（从 ASN.1 正文里抽出来的类型名摘要）用 SentenceTransformer 计算向量。 |
| **documents** | 完整 `chunk` 的 **JSON 字符串**（含 `message_releated`、`block_file`、`content_chunk`、`digested_asn_definitions` 等）。 |
| **metadatas** | `spec_number`、`version`、`message_releated`、`block_file`，用于 **metadata 过滤**。 |

要点：

- **没有单独建「关键词字段」或倒排索引**；向量与「全文」是分离的：向量来自类型名摘要，正文在 `documents` 的 JSON 里。
- 添加数据时传入自定义 `embeddings`，Chroma **不会**再对 `documents` 全文自动向量化。

---

## 二、向量检索（Chroma：`collection.query`）

1. 使用集合创建时绑定的 **同一套 embedding 函数**，把 **查询字符串** 编成查询向量。
2. 在 **`where` 元数据条件** 限定的子集上（例如当前 RRC 的 `spec_number` + `version`），按 **向量空间近邻** 排序并返回 Top-K。
3. 近邻度量由 collection 的 distance 配置决定（Chroma 常见为 L2；若向量已归一化，与余弦排序常单调相关）。

**小结**：向量这一路是 **语义/embedding 相似度检索**，不是全文 BM25。

---

## 三、「关键词检索」是什么（Chroma：`collection.get` + `where_document`）

实现上使用：

```text
where_document = { "$contains": query_text }
```

含义：

- 在已通过 **`where` 过滤** 的文档中，检查 **`documents` 整段字符串**（即那条 JSON）里是否 **包含查询串作为子串**。
- 典型情况：查询缺失的类型名（如 `MeasObjectEUTRA`）时，只要该字符串出现在 JSON 的 `content_chunk` 或 `digested_asn_definitions` 等字段的文本里，就可能被这一路召回。

**不是 BM25**：

- BM25 会基于词频、逆文档频率、文档长度等给出 **相关性分数并排序**。
- 当前 `$contains` 是 **子串命中过滤**，**没有** BM25 打分；命中顺序主要依赖 Chroma 返回顺序，后续由应用层的 RRF / rerank 使用。

---

## 四、Chroma 之外：混合与重排（应用代码）

Chroma 只负责：

1. **metadata 过滤**（`where`）；
2. **向量近邻 Top-K**（`query`）；
3. **全文子串过滤**（`get` + `where_document`）。

以下在 **Python 业务代码** 中完成，不是 Chroma 内置能力：

- **RRF（倒数排名融合）**：把「向量路返回的 id 顺序」与「关键词路返回的 id 顺序」合并成一路排序（`rag_db.py` 中 `_rrf_merge`）。
- **Qwen rerank**：对融合后的候选文本调用阿里云百炼兼容接口（`rerank_qwen.py`，默认 `qwen3-rerank`），需配置 `DASHSCOPE_API_KEY`。未配置时跳过 rerank，仅用 RRF 顺序截断。

可调环境变量见 `config.py`（如 `VEC_RECALL_K`、`KW_RECALL_K`、`RRF_K`、`RERANK_CANDIDATE_CAP`、`RERANK_MODEL`、`RERANK_INSTRUCT` 等）。

---

## 五、API 行为摘要（`query_asn1`）

- **`hybrid=True`（默认）**：向量 + `$contains` 两路召回，RRF 融合，可选 Qwen 重排。
- **`hybrid=False`**：仅向量召回，仍可选 rerank。
- **`use_rerank=True`（默认）**：在有关键的前提下调用 rerank；无 `DASHSCOPE_API_KEY` 时自动降级为仅 RRF 顺序。

---

## 六、一句话总结

**Chroma 当前负责：metadata 过滤 + 向量近邻 + 基于 document 全文的子串包含过滤；混合排序与精排由 RRF 与 Qwen rerank 在应用层完成；关键词这一路不是 BM25。**
