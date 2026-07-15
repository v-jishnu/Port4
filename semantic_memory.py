import chromadb
from dotenv import load_dotenv
from openai import OpenAI

from ticket_log import get_semantic_memory_candidates

load_dotenv()

CHROMA_PATH = "chroma_memory"
COLLECTION_NAME = "validated_tickets"
EMBEDDING_MODEL = "text-embedding-3-small"

# cosine distance (0 = identical, 2 = opposite); only trust a retrieved
# example if it's genuinely close, not just the "least far" of a bad batch
SIMILARITY_DISTANCE_THRESHOLD = 0.4

_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection = _client.get_or_create_collection(
    COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)
_openai_client = OpenAI()


def _embed(text: str) -> list[float]:
    response = _openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def sync_memory() -> int:
    """Batch sync: pull every human-validated ticket (admin_corrected or
    confidence_boosted) from ticket_log and upsert it into Chroma, keyed by
    the ticket's own id. Upsert (not insert) means re-syncing a ticket that
    was corrected again later replaces its old entry instead of leaving a
    stale duplicate behind. Returns the number of tickets synced."""
    candidates = get_semantic_memory_candidates()
    if not candidates:
        return 0

    ids = [c["id"] for c in candidates]
    embeddings = [_embed(c["input"]) for c in candidates]
    documents = [c["input"] for c in candidates]
    metadatas = [
        {
            "category": c["category"],
            "priority": c["priority"],
            "team": c["team"],
            "reasoning": c["reasoning"],
        }
        for c in candidates
    ]

    _collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    return len(candidates)


def retrieve_similar(ticket_text: str, k: int = 3) -> list[dict]:
    """Find up to k human-validated tickets similar to this one. Returns an
    empty list if memory is empty, or if nothing is similar enough to trust
    (see SIMILARITY_DISTANCE_THRESHOLD) - callers should treat an empty
    result as "no extra context available", not an error."""
    if _collection.count() == 0:
        return []

    query_embedding = _embed(ticket_text)
    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, _collection.count()),
    )

    similar = []
    for doc, metadata, distance in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        if distance <= SIMILARITY_DISTANCE_THRESHOLD:
            similar.append({"input": doc, "distance": distance, **metadata})
    return similar
