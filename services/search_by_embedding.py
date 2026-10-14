"""Optional generic vector search; callers must select their own index and filters."""
import logging
from clients import get_elasticsearch_client
from services.get_embeddings import get_embedding

logger = logging.getLogger(__name__)


def search_by_embedding(query_text: str, index: str, top_k: int = 1,
                        threshold: float = 0.6, filters=None):
    if not query_text or not query_text.strip() or not index or top_k < 1:
        return []
    vector = get_embedding(query_text)
    if not vector:
        return []
    client = get_elasticsearch_client()
    if client is None:
        return []
    try:
        knn = {"field": "embedding", "query_vector": vector, "k": top_k,
               "num_candidates": max(5, top_k * 2)}
        if filters is not None:
            knn["filter"] = filters
        response = client.search(index=index, body={"knn": knn}, size=top_k)
        return [hit['_source'] for hit in response['hits']['hits']
                if hit['_score'] >= threshold]
    except Exception:
        logger.warning('Optional Elasticsearch vector search failed')
        return []
    finally:
        client.close()
