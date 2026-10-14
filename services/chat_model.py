"""Local Ollama chat adapter for replies, JSON profiles and legacy tool handlers."""
import json
import uuid
from functools import lru_cache
from types import SimpleNamespace

import httpx
from config import Settings

settings = Settings()


class ToolCall(SimpleNamespace):
    def model_dump(self):
        return {'id': self.id, 'type': 'function', 'function': vars(self.function)}


class ChatClient:
    def health(self):
        result = {'provider': 'ollama', 'model': settings.OLLAMA_MODEL,
                  'embedding_model': settings.OLLAMA_EMBED_MODEL}
        try:
            for model in (settings.OLLAMA_MODEL, settings.OLLAMA_EMBED_MODEL):
                response = httpx.post(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/show',
                                      json={'model': model}, timeout=5)
                response.raise_for_status()
            result['status'] = 'ok'
        except httpx.HTTPError:
            result['status'] = 'unavailable'
        return result

    def generate(self, *, model=None, messages, tools=None, temperature=None,
                 response_format=None, timeout=None, stream=False):
        if stream:
            raise ValueError('Streaming is not supported by this chat handler')
        clean_messages = []
        names = {}
        for message in messages:
            clean = {'role': message['role'], 'content': message.get('content') or ''}
            calls = []
            for call in message.get('tool_calls') or []:
                function = call['function']
                names[call['id']] = function['name']
                arguments = function.get('arguments') or {}
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                calls.append({'function': {'name': function['name'], 'arguments': arguments}})
            if calls:
                clean['tool_calls'] = calls
            if message['role'] == 'tool':
                clean['tool_name'] = message.get('name') or names.get(message.get('tool_call_id'))
                if not clean['tool_name']:
                    raise ValueError('Tool response has no matching function name')
            clean_messages.append(clean)
        payload = {'model': settings.OLLAMA_MODEL, 'messages': clean_messages,
                   'stream': False, 'think': False, 'keep_alive': settings.OLLAMA_KEEP_ALIVE,
                   'options': {'num_ctx': settings.OLLAMA_NUM_CTX}}
        if temperature is not None:
            payload['options']['temperature'] = temperature
        if tools:
            payload['tools'] = tools
        if response_format and response_format.get('type') == 'json_object':
            payload['format'] = 'json'
        response = httpx.post(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/chat',
                              json=payload, timeout=timeout or settings.OLLAMA_TIMEOUT)
        response.raise_for_status()
        message = response.json()['message']
        calls = [ToolCall(id=call.get('id') or 'call_' + uuid.uuid4().hex,
                         function=SimpleNamespace(name=call['function']['name'],
                             arguments=json.dumps(call['function'].get('arguments') or {})))
                 for call in message.get('tool_calls') or []]
        content = message.get('content')
        if not content and not calls:
            raise RuntimeError('Ollama returned an empty reply')
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content or None, tool_calls=calls or None))])


@lru_cache(maxsize=1)
def get_chat_client():
    return ChatClient()


def make_chat_api_call(client, **kwargs):
    return client.generate(**kwargs)
