import unittest
from unittest.mock import patch, MagicMock

import httpx
from services.chat_model import ChatClient, settings
from services.get_embeddings import get_embedding


class OllamaTests(unittest.TestCase):
    @patch('services.chat_model.httpx.post')
    def test_chat_and_json_use_local_configured_model(self, post):
        post.return_value.json.return_value = {'message': {'content': '{"preferred_name":"Alex"}'}}
        result = ChatClient().generate(model='old-cloud-model',
            messages=[{'role':'user', 'content':'Hi'}],
            response_format={'type':'json_object'}, temperature=0)
        self.assertIn('Alex', result.choices[0].message.content)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], settings.OLLAMA_MODEL)
        self.assertEqual(payload['format'], 'json')
        self.assertFalse(payload['think'])
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['options']['temperature'], 0)
        self.assertTrue(post.call_args.args[0].endswith('/api/chat'))

    @patch('services.chat_model.httpx.post')
    def test_tool_call_round_trip(self, post):
        post.return_value.json.return_value = {'message': {'content':'', 'tool_calls':[
            {'function':{'name':'search', 'arguments':{'query':'London'}}}]}}
        client = ChatClient()
        call = client.generate(messages=[{'role':'user','content':'Find London'}],
                               tools=[{'type':'function','function':{'name':'search'}}]).choices[0].message.tool_calls[0]
        self.assertEqual(call.function.arguments, '{"query": "London"}')
        history = [{'role':'assistant','content':None,'tool_calls':[dict(call.model_dump(),gemini_part='old')]},
                   {'role':'tool','tool_call_id':call.id,'content':'found'}]
        client.generate(messages=history)
        messages = post.call_args.kwargs['json']['messages']
        self.assertEqual(messages[1]['tool_name'], 'search')
        self.assertEqual(messages[0]['tool_calls'][0]['function']['arguments'], {'query':'London'})
        self.assertNotIn('gemini_part', str(messages))

    @patch('services.chat_model.httpx.post', side_effect=httpx.ConnectError('offline'))
    def test_outage_is_reported_without_cloud_fallback(self, post):
        self.assertEqual(ChatClient().health()['status'], 'unavailable')
        with self.assertRaises(httpx.ConnectError):
            ChatClient().generate(messages=[{'role':'user','content':'Hi'}])

    @patch('services.chat_model.httpx.post')
    def test_health_checks_both_models(self, post):
        self.assertEqual(ChatClient().health()['status'], 'ok')
        self.assertEqual([c.kwargs['json']['model'] for c in post.call_args_list],
                         [settings.OLLAMA_MODEL, settings.OLLAMA_EMBED_MODEL])

    @patch('services.get_embeddings.httpx.post')
    def test_embeddings_prefix_dimension_and_failure(self, post):
        post.return_value.json.return_value = {'embeddings': [[0.1]*768]}
        self.assertEqual(len(get_embedding('hello')), 768)
        self.assertEqual(post.call_args.kwargs['json']['input'], 'search_query: hello')
        get_embedding('profile', 'RETRIEVAL_DOCUMENT')
        self.assertEqual(post.call_args.kwargs['json']['input'], 'search_document: profile')
        post.return_value.json.return_value = {'embeddings': [[0.1]*10]}
        self.assertEqual(get_embedding('hello'), [])
        post.side_effect = httpx.ConnectError('offline')
        self.assertEqual(get_embedding('hello'), [])
