"""Local Ollama embeddings shared by profile memory and optional vector search."""
import logging
from typing import List

import httpx
from config import Settings

settings = Settings()
logger = logging.getLogger(__name__)


def get_embedding(text: str, task_type: str = 'RETRIEVAL_QUERY') -> List[float]:
    if not text.strip():
        return []
    # Nomic's retrieval prefixes distinguish queries from indexed documents.
    if settings.OLLAMA_EMBED_MODEL.split(':')[0] == 'nomic-embed-text':
        prefix = 'search_query' if task_type == 'RETRIEVAL_QUERY' else 'search_document'
        text = f'{prefix}: {text}'
    try:
        response = httpx.post(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/embed',
            json={'model': settings.OLLAMA_EMBED_MODEL, 'input': text,
                  'keep_alive': settings.OLLAMA_KEEP_ALIVE}, timeout=settings.OLLAMA_TIMEOUT)
        response.raise_for_status()
        vector = response.json()['embeddings'][0]
        if len(vector) != 768:
            raise ValueError('The configured embedding model must return 768 dimensions')
        return vector
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        logger.warning('Ollama embedding unavailable; check server and embedding model')
        return []
