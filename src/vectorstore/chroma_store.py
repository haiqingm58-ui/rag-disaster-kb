import hashlib
import math
import re
from typing import List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.embeddings import Embeddings

from config import (
    CHROMA_DIR,
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    COLLECTION_DOCS,
    COLLECTION_EVENTS,
    RETRIEVAL_K_DOCS,
    validate_embedding_config,
)

_embeddings: Optional[Embeddings] = None


class HashEmbeddings(Embeddings):
    """Small deterministic embedding backend for low-memory deployments.

    It is not a replacement for a semantic embedding model, but it gives Chroma
    a useful keyword/character-ngram vector when Ollama or a remote embedding
    API is unavailable.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        words = re.findall(r"[a-z0-9]+", lowered)
        chars = [ch for ch in lowered if "\u4e00" <= ch <= "\u9fff"]
        grams = chars[:]
        grams.extend("".join(chars[i:i + 2]) for i in range(max(0, len(chars) - 1)))
        grams.extend("".join(chars[i:i + 3]) for i in range(max(0, len(chars) - 2)))
        return words + grams

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            sign = 1.0 if (value >> 8) & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _get_embeddings() -> Embeddings:
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    validate_embedding_config()

    if EMBEDDING_PROVIDER == "hash":
        _embeddings = HashEmbeddings()
    elif EMBEDDING_PROVIDER in {"openai", "openai_compatible"}:
        api_key = EMBEDDING_API_KEY or OPENAI_API_KEY
        base_url = EMBEDDING_BASE_URL or OPENAI_BASE_URL
        _embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=api_key,
            base_url=base_url,
        )
    else:
        _embeddings = OllamaEmbeddings(
            model=OLLAMA_EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
        )

    return _embeddings


def embedding_config_status() -> dict:
    """Return a lightweight embedding configuration status without making network calls."""
    try:
        validate_embedding_config()
        return {
            "ready": True,
            "provider": EMBEDDING_PROVIDER,
            "model": (
                OLLAMA_EMBED_MODEL
                if EMBEDDING_PROVIDER == "ollama"
                else "hash-384"
                if EMBEDDING_PROVIDER == "hash"
                else EMBEDDING_MODEL
            ),
            "message": "embedding 配置完整",
        }
    except Exception as exc:
        return {
            "ready": False,
            "provider": EMBEDDING_PROVIDER,
            "model": (
                OLLAMA_EMBED_MODEL
                if EMBEDDING_PROVIDER == "ollama"
                else "hash-384"
                if EMBEDDING_PROVIDER == "hash"
                else EMBEDDING_MODEL
            ),
            "message": str(exc),
        }


def get_chroma(collection_name: str) -> Chroma:
    return Chroma(
        collection_name=collection_name,
        embedding_function=_get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def add_documents(documents: List[Document], collection_name: str) -> None:
    if not documents:
        return
    store = get_chroma(collection_name)
    store.add_documents(documents)


def add_documents_with_ids(
    documents: List[Document],
    ids: List[str],
    collection_name: str,
) -> None:
    """Add documents with stable IDs so realtime events can be deduplicated."""
    if not documents:
        return
    store = get_chroma(collection_name)
    store.add_documents(documents, ids=ids)


def collection_ids(collection_name: str) -> set[str]:
    """Return all document IDs in a collection."""
    store = get_chroma(collection_name)
    try:
        results = store.get(include=[])
        return set(results.get("ids", []))
    except Exception:
        return set()


def get_retriever(collection_name: str, k: int = RETRIEVAL_K_DOCS) -> VectorStoreRetriever:
    store = get_chroma(collection_name)
    return store.as_retriever(search_kwargs={"k": k})


def retrieve_with_scores(
    query: str,
    collection_name: str,
    k: int = RETRIEVAL_K_DOCS,
) -> List[Tuple[Document, float]]:
    """Retrieve documents with similarity scores."""
    store = get_chroma(collection_name)
    return store.similarity_search_with_score(query, k=k)


def list_sources(collection_name: str) -> List[str]:
    """List unique source file paths in a collection."""
    store = get_chroma(collection_name)
    try:
        results = store.get(include=["metadatas"])
        metadatas = results.get("metadatas", [])
        if not metadatas:
            return []
        sources = set()
        for m in metadatas:
            src = m.get("source", "")
            if src:
                sources.add(src)
        return sorted(sources)
    except Exception:
        return []


def source_chunk_count(collection_name: str, source: str) -> int:
    """Count chunks from a specific source."""
    store = get_chroma(collection_name)
    try:
        results = store.get(include=["metadatas"], where={"source": source})
        metadatas = results.get("metadatas", [])
        return len(metadatas)
    except Exception:
        return 0


def delete_by_source(collection_name: str, source: str) -> int:
    """Delete all chunks from a specific source. Returns count deleted."""
    count = source_chunk_count(collection_name, source)
    if count > 0:
        store = get_chroma(collection_name)
        store._collection.delete(where={"source": source})
    return count


def delete_collection(collection_name: str) -> None:
    store = get_chroma(collection_name)
    store.delete_collection()


def collection_count(collection_name: str) -> int:
    store = get_chroma(collection_name)
    try:
        return store._collection.count()
    except Exception:
        return 0


def get_docs_collection() -> Chroma:
    return get_chroma(COLLECTION_DOCS)


def get_events_collection() -> Chroma:
    return get_chroma(COLLECTION_EVENTS)
