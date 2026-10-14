"""Optional Redis and Elasticsearch connections, initialized only when requested."""
import logging
import redis
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ApiError, TransportError
from config import Settings

settings = Settings()
logger = logging.getLogger(__name__)


def get_redis_client():
    client = None
    try:
        client = redis.Redis(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT,
            username=settings.REDIS_USERNAME or None, password=settings.REDIS_PASSWORD or None,
            ssl=settings.REDIS_SSL, decode_responses=True, max_connections=20,
            socket_timeout=settings.REDIS_TIMEOUT, socket_connect_timeout=settings.REDIS_TIMEOUT,
            socket_keepalive=True, health_check_interval=15)
        client.ping()
        return client
    except (redis.RedisError, ValueError):
        if client is not None:
            client.close()
        logger.warning("Redis is unavailable; check optional infrastructure configuration")
        return None


def get_elasticsearch_client():
    client = None
    try:
        client = Elasticsearch(settings.ELASTICSEARCH_URL,
                               request_timeout=settings.ELASTICSEARCH_TIMEOUT,
                               max_retries=0)
        client.info()
        return client
    except (ApiError, TransportError, ValueError):
        if client is not None:
            client.close()
        logger.warning("Elasticsearch is unavailable; check optional infrastructure configuration")
        return None
