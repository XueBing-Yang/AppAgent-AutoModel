"""
长期语义记忆存储模块。
使用 DashScope text-embedding API 将记忆向量化，以 JSON 持久化存储，
支持基于余弦相似度的语义检索。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai
from dotenv import load_dotenv

load_dotenv()


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """纯 Python 实现余弦相似度。"""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryStore:
    """长期语义记忆存储：向量化、检索、JSON 持久化。"""

    def __init__(
        self,
        path: str = "data/agent_memory.json",
        max_memories: int = 500,
        retrieval_top_k: int = 5,
        embedding_model: str = "text-embedding-v3",
        dimensions: int = 1024,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.path = Path(path)
        self.max_memories = max_memories
        self.retrieval_top_k = retrieval_top_k
        self.embedding_model = embedding_model
        self.dimensions = dimensions

        self.memories: List[Dict[str, Any]] = []
        self._embedding_client: Optional[openai.OpenAI] = None

        api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if api_key:
            self._embedding_client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=60.0,
            )
        self.load()

    def _embed(self, text: str) -> List[float]:
        """调用 DashScope embedding API 获取文本向量。"""
        if not self._embedding_client:
            return []
        text = (text or "").strip()
        if not text:
            return []
        try:
            resp = self._embedding_client.embeddings.create(
                model=self.embedding_model,
                input=text[:8192],
                dimensions=self.dimensions,
                encoding_format="float",
            )
            data = resp.data
            if data and len(data) > 0:
                return list(data[0].embedding)
        except Exception:
            pass
        return []

    def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        添加一条记忆：向量化后写入内存。
        返回记忆 id，失败返回 None。
        """
        content = (content or "").strip()
        if not content:
            return None
        content = content[:500]
        embedding = self._embed(content)
        if not embedding:
            return None
        mem_id = str(uuid.uuid4())
        mem = {
            "id": mem_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "embedding": embedding,
        }
        self.memories.append(mem)
        while len(self.memories) > self.max_memories:
            self.memories.pop(0)
        return mem_id

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        语义检索：对 query 向量化，计算与各记忆的余弦相似度，返回 top_k 条。
        返回项包含 content、timestamp、metadata，不含 embedding。
        """
        k = top_k if top_k is not None else self.retrieval_top_k
        if not self.memories or k <= 0:
            return []
        query_emb = self._embed(query)
        if not query_emb:
            return []
        scored: List[tuple] = []
        for m in self.memories:
            emb = m.get("embedding") or []
            if len(emb) != len(query_emb):
                continue
            sim = _cosine_similarity(query_emb, emb)
            scored.append((sim, m))
        scored.sort(key=lambda x: -x[0])
        result = []
        for _, m in scored[:k]:
            result.append({
                "id": m.get("id"),
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp", ""),
                "metadata": m.get("metadata", {}),
            })
        return result

    def save(self) -> None:
        """持久化到 JSON 文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "memories": self.memories,
            "embedding_model": self.embedding_model,
            "dimensions": self.dimensions,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        """从 JSON 文件加载。"""
        if not self.path.exists():
            self.memories = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.memories = data.get("memories", [])
            if not isinstance(self.memories, list):
                self.memories = []
        except Exception:
            self.memories = []
