"""Optional read-only Redis history helper; active conversation storage uses SQLite."""
import json
from clients import get_redis_client
from config import Settings


def get_chat_history(user_id: str, conversation_id: str, max_messages: int = 100):
    if max_messages < 1:
        return []
    client = get_redis_client()
    if client is None:
        return []
    # JSON encoding keeps user and conversation IDs unambiguous in the key.
    key = Settings().REDIS_KEY_PREFIX + ':messages:' + json.dumps([user_id, conversation_id])
    try:
        history = []
        for raw in client.lrange(key, -max_messages, -1):
            try:
                message = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if (isinstance(message, dict) and message.get('role') in {'user', 'assistant'}
                    and isinstance(message.get('content'), str)):
                history.append({'role': message['role'], 'content': message['content']})
        return history
    finally:
        client.close()
