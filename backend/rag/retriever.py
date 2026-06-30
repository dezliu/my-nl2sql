"""Qdrant hybrid search: BM25 sparse + dense vectors + RRF fusion."""

import uuid
from dataclasses import dataclass

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from backend.config import settings

DENSE_DIM = 384
COLLECTION = settings.qdrant_collection


@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    doc_type: str
    metadata: dict


class HybridRetriever:
    def __init__(self) -> None:
        # Local Qdrant must bypass system HTTP/SOCKS proxy (otherwise 502 Bad Gateway).
        self.client = QdrantClient(
            url=settings.qdrant_url,
            check_compatibility=False,
            trust_env=False,
        )
        self.dense_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION not in collections:
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config={
                    "dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
                },
            )

    def _embed_dense(self, text: str) -> list[float]:
        vec = next(self.dense_model.embed([text]))
        return [float(x) for x in vec]

    def _embed_sparse(self, text: str) -> SparseVector:
        result = next(self.sparse_model.embed([text]))
        return SparseVector(indices=result.indices.tolist(), values=result.values.tolist())

    def index_document(
        self,
        content: str,
        doc_type: str,
        chunk_id: int,
        datasource_id: int | None = None,
        metadata: dict | None = None,
    ) -> str:
        point_id = str(uuid.uuid4())
        payload = {
            "chunk_id": chunk_id,
            "content": content,
            "doc_type": doc_type,
            "datasource_id": datasource_id,
            **(metadata or {}),
        }
        self.client.upsert(
            collection_name=COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector={
                        "dense": self._embed_dense(content),
                        "sparse": self._embed_sparse(content),
                    },
                    payload=payload,
                )
            ],
        )
        return point_id

    def search(
        self,
        query: str,
        top_k: int | None = None,
        datasource_id: int | None = None,
    ) -> list[RetrievedChunk]:
        k = top_k or settings.rag_top_k
        query_filter = None
        if datasource_id is not None:
            query_filter = Filter(
                must=[FieldCondition(key="datasource_id", match=MatchValue(value=datasource_id))]
            )

        dense_vec = self._embed_dense(query)
        sparse_vec = self._embed_sparse(query)

        results = self.client.query_points(
            collection_name=COLLECTION,
            prefetch=[
                Prefetch(query=dense_vec, using="dense", limit=k * 2),
                Prefetch(query=sparse_vec, using="sparse", limit=k * 2),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=query_filter,
            limit=k,
            with_payload=True,
        )

        chunks: list[RetrievedChunk] = []
        for point in results.points:
            payload = point.payload or {}
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(payload.get("chunk_id", point.id)),
                    content=payload.get("content", ""),
                    score=point.score or 0.0,
                    doc_type=payload.get("doc_type", "unknown"),
                    metadata={k: v for k, v in payload.items() if k not in ("content", "chunk_id")},
                )
            )
        return chunks

    def delete_by_chunk_id(self, chunk_id: int) -> None:
        self.client.delete(
            collection_name=COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]
            ),
        )
