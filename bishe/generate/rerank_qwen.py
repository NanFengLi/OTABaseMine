"""
使用阿里云百炼 DashScope 兼容 OpenAI 的 rerank 接口（qwen3-rerank 等）对候选文档重排。
文档：https://help.aliyun.com/zh/model-studio/developer-reference/text-rerank-api
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import List, Optional

try:
    from bishe.generate.config import Config
except ImportError:
    from config import Config

logger = logging.getLogger(__name__)

DASHSCOPE_RERANK_URL = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"

# 单条文档送入 rerank 的最大字符数（避免超长；模型单条约 4k tokens）
RERANK_DOC_MAX_CHARS = int(os.getenv("RERANK_DOC_MAX_CHARS", "12000"))


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def rerank_document_indices(
    query: str,
    documents: List[str],
    top_n: int,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    instruct: Optional[str] = None,
    timeout_sec: float = 60.0,
) -> Optional[List[int]]:
    """
    调用 qwen rerank，返回按相关性排序后的「输入 documents 的下标」列表（长度不超过 top_n）。

    失败时返回 None，由调用方回退到融合排序。
    """
    if not documents:
        return []
    key = api_key or Config.DASHSCOPE_API_KEY
    if not key:
        logger.warning("未配置 DASHSCOPE_API_KEY，跳过 rerank")
        return None

    model_name = model or Config.RERANK_MODEL
    instruct = instruct if instruct is not None else Config.RERANK_INSTRUCT

    payload_docs = [_truncate(d, RERANK_DOC_MAX_CHARS) for d in documents]
    body = {
        "model": model_name,
        "query": query,
        "documents": payload_docs,
        "top_n": min(top_n, len(documents)),
    }
    if instruct:
        body["instruct"] = instruct

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        DASHSCOPE_RERANK_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        logger.error("rerank HTTP 错误 %s: %s", e.code, err_body)
        return None
    except Exception as e:
        logger.error("rerank 请求失败: %s", e)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("rerank 响应非 JSON: %s", raw[:500])
        return None

    if parsed.get("code") and parsed.get("code") not in ("", None):
        logger.error("rerank API 错误: %s %s", parsed.get("code"), parsed.get("message"))
        return None

    results = None
    out = parsed.get("output")
    if isinstance(out, dict) and "results" in out:
        results = out["results"]
    elif "results" in parsed:
        results = parsed["results"]
    elif isinstance(parsed.get("data"), list):
        results = parsed["data"]

    if not results:
        logger.error("rerank 响应缺少 results: %s", raw[:800])
        return None

    indices: List[int] = []
    for item in results:
        if isinstance(item, dict) and "index" in item:
            indices.append(int(item["index"]))
        else:
            logger.warning("rerank 结果项格式异常: %s", item)

    if not indices:
        return None
    return indices[:top_n]
