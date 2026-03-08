"""
DevOps Butler - RAG Layer (Knowledge Retrieval)
FAISS-based vector search over curated failure stories and best practices.
Uses Titan Embeddings V2 for encoding.
"""

import os
import json
import logging
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np

from config.logging_config import get_logger
from config.settings import get_settings

logger = get_logger("rag")

# Knowledge base directory
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"


class RAGLayer:
    """
    Simple but effective RAG layer using FAISS + Titan Embeddings.
    
    At startup:
        1. Loads all markdown files from knowledge/
        2. Chunks them into paragraphs
        3. Embeds with Titan Embeddings V2
        4. Stores in FAISS index
        
    At query time:
        1. Embed query with Titan
        2. Search FAISS for top-k similar chunks
        3. Return relevant context
    """

    def __init__(self, knowledge_dir: Optional[str] = None):
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else KNOWLEDGE_DIR
        self.documents: List[Dict[str, str]] = []  # {"text": ..., "source": ..., "title": ...}
        self.embeddings: Optional[np.ndarray] = None
        self.index = None  # FAISS index
        self._is_loaded = False

    def load(self, trace_id: str = "no-trace") -> None:
        """Load knowledge base and build FAISS index."""
        if self._is_loaded:
            return

        # Check for cached index
        cache_path = self.knowledge_dir / ".cache" / "faiss_index.pkl"
        if cache_path.exists():
            try:
                self._load_cache(cache_path)
                logger.info(
                    f"Loaded cached FAISS index ({len(self.documents)} docs)",
                    extra={"trace_id": trace_id}
                )
                self._is_loaded = True
                return
            except Exception as e:
                logger.warning(f"Cache load failed, rebuilding: {e}", extra={"trace_id": trace_id})

        # Load documents
        self.documents = self._load_documents(trace_id)
        if not self.documents:
            logger.warning("No knowledge documents found", extra={"trace_id": trace_id})
            self._is_loaded = True
            return

        # Embed all documents
        self._build_index(trace_id)
        self._is_loaded = True

        # Save cache
        try:
            self._save_cache(cache_path)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}", extra={"trace_id": trace_id})

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        trace_id: str = "no-trace",
    ) -> List[Dict[str, Any]]:
        """
        Query the knowledge base for relevant documents.
        
        Returns:
            List of {"text": ..., "source": ..., "title": ..., "score": ...}
        """
        if not self._is_loaded:
            self.load(trace_id)

        if not self.documents or self.index is None:
            return []

        try:
            from generators.bedrock_client import get_bedrock_client
            query_embedding = get_bedrock_client().embed_text(query_text, trace_id=trace_id)
            query_vector = np.array([query_embedding], dtype=np.float32)

            # Search FAISS
            import faiss
            scores, indices = self.index.search(query_vector, min(top_k, len(self.documents)))

            results = []
            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < len(self.documents) and idx >= 0:
                    doc = dict(self.documents[idx])
                    doc["score"] = float(score)
                    results.append(doc)

            logger.info(
                f"RAG query returned {len(results)} results",
                extra={"trace_id": trace_id}
            )
            return results

        except Exception as e:
            logger.error(f"RAG query failed: {e}", extra={"trace_id": trace_id})
            return []

    def _load_documents(self, trace_id: str) -> List[Dict[str, str]]:
        """Load and chunk all markdown files from knowledge directory."""
        documents = []

        if not self.knowledge_dir.exists():
            logger.info(
                f"Knowledge directory not found: {self.knowledge_dir}",
                extra={"trace_id": trace_id}
            )
            return documents

        for md_path in self.knowledge_dir.rglob("*.md"):
            if md_path.name.startswith("."):
                continue
                
            try:
                content = md_path.read_text(encoding="utf-8", errors="replace")
                relative_path = md_path.relative_to(self.knowledge_dir)
                
                # Extract title from first H1
                title = md_path.stem
                for line in content.split("\n"):
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

                # Chunk by paragraphs (split on double newlines)
                chunks = self._chunk_text(content, max_chunk_size=500)
                
                for i, chunk in enumerate(chunks):
                    if chunk.strip():
                        documents.append({
                            "text": chunk.strip(),
                            "source": str(relative_path),
                            "title": title,
                            "chunk_index": i,
                        })

            except Exception as e:
                logger.warning(
                    f"Failed to load {md_path}: {e}",
                    extra={"trace_id": trace_id}
                )

        logger.info(
            f"Loaded {len(documents)} chunks from knowledge base",
            extra={"trace_id": trace_id}
        )
        return documents

    def _chunk_text(self, text: str, max_chunk_size: int = 500) -> List[str]:
        """Split text into chunks by paragraphs, respecting max size."""
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= max_chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _build_index(self, trace_id: str) -> None:
        """Build FAISS index from documents."""
        try:
            import faiss
            from generators.bedrock_client import get_bedrock_client

            client = get_bedrock_client()
            texts = [doc["text"] for doc in self.documents]

            logger.info(
                f"Embedding {len(texts)} chunks with Titan...",
                extra={"trace_id": trace_id}
            )
            
            embeddings_list = client.embed_texts(texts, trace_id=trace_id)
            self.embeddings = np.array(embeddings_list, dtype=np.float32)

            # Build FAISS index (inner product for normalized vectors = cosine similarity)
            dimension = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
            self.index.add(self.embeddings)

            logger.info(
                f"FAISS index built: {self.index.ntotal} vectors, {dimension}-dim",
                extra={"trace_id": trace_id}
            )

        except ImportError:
            logger.warning(
                "faiss-cpu not installed, RAG disabled",
                extra={"trace_id": trace_id}
            )
        except Exception as e:
            logger.error(
                f"Failed to build FAISS index: {e}",
                extra={"trace_id": trace_id}
            )

    def _save_cache(self, cache_path: Path) -> None:
        """Save index to disk cache."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump({
                "documents": self.documents,
                "embeddings": self.embeddings,
            }, f)

    def _load_cache(self, cache_path: Path) -> None:
        """Load index from disk cache."""
        import faiss
        
        with open(cache_path, "rb") as f:
            data = pickle.load(f)
        
        self.documents = data["documents"]
        self.embeddings = data["embeddings"]
        
        if self.embeddings is not None and len(self.embeddings) > 0:
            dimension = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)
            self.index.add(self.embeddings)


# ── Singleton ───────────────────────────────────────────────────────────
_rag_layer: Optional[RAGLayer] = None


def get_rag_layer() -> RAGLayer:
    global _rag_layer
    if _rag_layer is None:
        _rag_layer = RAGLayer()
    return _rag_layer
