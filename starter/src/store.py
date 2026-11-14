"""Store and search vectors using PostgreSQL + pgvector."""
from typing import Any
import psycopg
from .models import Chunk

FILTER_COLUMNS = {"platform", "section"}


def to_pgvector(vector: list[float]) -> str:
    """Write a Python list in pgvector's text form, e.g. [0.1,-0.2,0.3]."""
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        """Retain connection settings; validate model dimensions."""
        if not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("dimensions must be a positive int")
        self.database_url = database_url
        self.dimensions = dimensions

    def create_schema(self) -> None:
        """Create the chunks table with a vector column and source/page/filter metadata."""
        with psycopg.connect(self.database_url) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    strategy    text NOT NULL,
                    chunk_id    text NOT NULL,
                    document_id text NOT NULL,
                    source      text NOT NULL,
                    page        int  NOT NULL,
                    section     text,
                    platform    text,
                    text        text NOT NULL,
                    embedding   vector({self.dimensions}) NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )
            """)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate lengths/dimensions and write stable IDs without duplicates.

        When re-ingesting changed source documents, remove obsolete chunks too.
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.dimensions:
                raise ValueError(f"{chunk.chunk_id}: vector has {len(vector)} dims, expected {self.dimensions}")

        with psycopg.connect(self.database_url) as conn:
            for chunk, vector in zip(chunks, vectors):
                conn.execute(
                    """
                    INSERT INTO chunks (strategy, chunk_id, document_id, source, page,
                                        section, platform, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source      = EXCLUDED.source,
                        page        = EXCLUDED.page,
                        section     = EXCLUDED.section,
                        platform    = EXCLUDED.platform,
                        text        = EXCLUDED.text,
                        embedding   = EXCLUDED.embedding
                    """,
                    (strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
                     chunk.metadata.get("section"), chunk.metadata.get("platform"),
                     chunk.text, to_pgvector(vector)),
                )
            for document_id in {chunk.document_id for chunk in chunks}:
                keep = [chunk.chunk_id for chunk in chunks if chunk.document_id == document_id]
                conn.execute(
                    "DELETE FROM chunks WHERE strategy = %s AND document_id = %s AND NOT (chunk_id = ANY(%s))",
                    (strategy, document_id, keep),
                )

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Filter permitted metadata in SQL, rank by cosine distance, return top-k.

        Return chunk ID, text, score and metadata. Parameterize user-supplied values.
        """
        if len(query_vector) != self.dimensions:
            raise ValueError(f"query vector has {len(query_vector)} dims, expected {self.dimensions}")
        where = ["strategy = %s"]
        params: list[Any] = [strategy]
        for column, value in (filters or {}).items():
            if column not in FILTER_COLUMNS:
                raise ValueError(f"cannot filter on {column!r}; allowed: {sorted(FILTER_COLUMNS)}")
            where.append(f"{column} = %s")
            params.append(value)
        qv = to_pgvector(query_vector)
        sql = f"""
            SELECT chunk_id, document_id, source, page, section, platform, text,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE {" AND ".join(where)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(sql, [qv, *params, qv, top_k]).fetchall()
        return [
            {"chunk_id": r[0], "document_id": r[1], "source": r[2], "page": r[3],
             "metadata": {"section": r[4], "platform": r[5]}, "text": r[6], "score": float(r[7])}
            for r in rows
        ]
