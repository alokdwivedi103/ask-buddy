import json
import hashlib
import hmac
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import app
from database import settings as db_settings
from services import profile_store as store
from services import personal_chat
from routers import whatsapp_router
from config import Settings


class PersonalChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db_settings, 'DB_SQLITE_PATH', str(Path(self.tmp.name)/'test.db'))
        self.db_patch.start()
        self.client = TestClient(app)
        self.client.__enter__()
        self.headers = {'x-api-key': Settings().API_KEY}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.db_patch.stop()
        self.tmp.cleanup()

    def user(self, consent=True):
        response = self.client.post('/profiles', headers=self.headers,
                                    json={'memory_consent': consent})
        self.assertEqual(response.status_code, 201)
        return response.json()['user_id']

    def test_endpoints_require_auth(self):
        self.assertEqual(self.client.post('/profiles', json={}).status_code, 422)
        self.assertEqual(self.client.get('/profiles/unknown', headers={'x-api-key':'wrong'}).status_code, 403)

    @patch('services.personal_chat.embed', return_value=[1., 0.])
    @patch('services.personal_chat.learn_profile', return_value={'preferred_name':'Alex', 'goals':['Sleep better']})
    @patch('services.personal_chat.generate', return_value='What has been making sleep difficult?')
    def test_profile_learning_memory_and_isolation(self, generate, learn, embed):
        alice, bob = self.user(), self.user()
        response = self.client.post('/chat/chat', headers=self.headers,
            json={'user_id':alice, 'conversation_id':'same', 'message':'I want to sleep better'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.get_user(alice)['profile']['preferred_name'], 'Alex')
        self.assertEqual(len(store.history(alice,'same')), 2)
        self.assertEqual(store.history(bob,'same'), [])
        self.assertEqual(store.relevant_memories(bob,[1.,0.]), [])
        self.assertEqual(len(store.relevant_memories(alice,[1.,0.])),1)
        personal_chat.chat(bob,'same','Hello')
        self.assertNotIn('Alex', str(generate.call_args.args[0]))

    @patch('services.personal_chat.embed')
    @patch('services.personal_chat.learn_profile')
    @patch('services.personal_chat.generate', return_value='I am listening.')
    def test_no_consent_does_not_persist_or_embed(self, generate, learn, embed):
        user = self.user(False)
        personal_chat.chat(user, 'one', 'Sensitive message', [{'role':'user','content':'Earlier'}])
        self.assertEqual(store.history(user,'one'), [])
        self.assertEqual(store.get_user(user)['profile'], {})
        self.assertIn('Earlier',str(generate.call_args.args[0]))
        embed.assert_not_called()
        learn.assert_not_called()

    def test_opt_out_erases_all_saved_content(self):
        user = self.user()
        store.save_turn(user,'one','Private','Reply')
        store.save_memory(user,'private',[1.,0.],'profile')
        response = self.client.put('/profiles/'+user, headers=self.headers,
                                   json={'memory_consent':False})
        self.assertEqual(response.status_code,200)
        self.assertEqual(store.history(user,'one'),[])
        self.assertEqual(store.relevant_memories(user,[1.,0.]),[])
        self.assertEqual(store.get_user(user)['profile'],{})
        self.assertEqual(self.client.delete('/profiles/'+user,headers=self.headers).status_code,204)
        self.assertIsNone(store.get_user(user))

    def test_unknown_profile_and_blank_chat(self):
        self.assertEqual(self.client.post('/chat/chat',headers=self.headers,
            json={'user_id':'unknown','message':'Hi'}).status_code,404)
        user=self.user()
        self.assertEqual(self.client.post('/chat/chat',headers=self.headers,
            json={'user_id':user,'message':'   '}).status_code,422)

    def test_signature_verification_and_event_deduplication(self):
        with patch.object(whatsapp_router.settings,'WHATSAPP_APP_SECRET','test-secret'):
            body=b'{"example":true}'
            signature='sha256='+hmac.new(b'test-secret',body,hashlib.sha256).hexdigest()
            self.assertTrue(whatsapp_router.valid_signature(body,signature))
            self.assertFalse(whatsapp_router.valid_signature(body+b' ',signature))
        self.assertTrue(store.claim_event('evt1'))
        self.assertFalse(store.claim_event('evt1'))

    @patch('routers.whatsapp_router.process_message')
    def test_signed_webhook_accepts_once_and_checks_target(self, process):
        with patch.multiple(whatsapp_router.settings, WHATSAPP_APP_SECRET='secret',
                            WHATSAPP_ACCESS_TOKEN='token', WHATSAPP_PHONE_NUMBER_ID='123',
                            WHATSAPP_API_VERSION='v-test'):
            payload={'object':'whatsapp_business_account','entry':[{'changes':[{'value':{
                'metadata':{'phone_number_id':'123'},
                'messages':[{'type':'text','id':'evt2','from':'456','text':{'body':'Hello'}}]
            }}]}]}
            body=json.dumps(payload).encode()
            signature='sha256='+hmac.new(b'secret',body,hashlib.sha256).hexdigest()
            headers={'x-hub-signature-256':signature,'Content-Type':'application/json'}
            self.assertEqual(self.client.post('/webhooks/whatsapp',content=body,headers=headers).status_code,200)
            self.assertEqual(self.client.post('/webhooks/whatsapp',content=body,headers=headers).status_code,200)
            process.assert_called_once()
            self.assertEqual(self.client.post('/webhooks/whatsapp',content=body,
                headers={'x-hub-signature-256':'wrong'}).status_code,403)

    def test_webhook_verification_challenge(self):
        with patch.object(whatsapp_router.settings,'WHATSAPP_VERIFY_TOKEN','verify-secret'):
            response=self.client.get('/webhooks/whatsapp',params={
                'hub.mode':'subscribe','hub.verify_token':'verify-secret','hub.challenge':'12345'})
            self.assertEqual(response.text,'12345')
            self.assertEqual(self.client.get('/webhooks/whatsapp',params={
                'hub.mode':'subscribe','hub.verify_token':'wrong'}).status_code,403)

    @patch('routers.personal_router.embed',return_value=[])
    def test_profile_correction_removes_stale_vectors(self, embed):
        user=self.user()
        store.save_memory(user,'Old information',[1.,0.],'profile')
        response=self.client.put('/profiles/'+user,headers=self.headers,json={
            'memory_consent':True,'profile':{'preferred_name':'New name'}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(store.get_user(user)['profile']['preferred_name'],'New name')
        self.assertEqual(store.relevant_memories(user,[1.,0.]),[])

    @patch('services.personal_chat.embed',return_value=[])
    @patch('services.personal_chat.learn_profile',return_value={})
    @patch('services.personal_chat.generate',return_value='I hear you.')
    def test_embedding_failure_keeps_chat_available(self, generate, learn, embed):
        user=self.user()
        result=personal_chat.chat(user,'session','Hello')
        self.assertEqual(result['reply'],'I hear you.')
        self.assertEqual(result['memory_status'],'embedding_unavailable')
        self.assertEqual(len(store.history(user,'session')),2)

    def test_saved_conversations_and_complete_history_are_user_scoped(self):
        alice, bob = self.user(), self.user()
        for index in range(55):
            store.save_turn(alice, 'older', f'message {index}', 'reply')
        store.save_turn(alice, 'latest', 'Recent chat', 'Reply')
        store.save_turn(bob, 'private', 'Bob secret', 'Reply')
        response = self.client.get('/chat/conversations/'+alice, headers=self.headers)
        self.assertEqual([c['conversation_id'] for c in response.json()['conversations']],
                         ['latest', 'older'])
        history = self.client.get('/chat/history/'+alice+'/older', headers=self.headers)
        self.assertEqual(len(history.json()['messages']), 110)
        self.assertEqual(history.json()['messages'][0]['content'], 'message 0')
        self.assertEqual(self.client.get('/chat/history/'+alice+'/private',
                         headers=self.headers).json()['messages'], [])
        self.assertEqual(self.client.get('/chat/conversations/unknown', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/chat/conversations/'+alice,
                         headers={'x-api-key':'wrong'}).status_code, 403)

    @patch('services.personal_chat.embed', return_value=[])
    @patch('services.personal_chat.learn_profile', return_value={})
    @patch('services.personal_chat.generate', return_value='I remember our discussion.')
    def test_new_conversation_uses_prior_chats_without_other_users(self, generate, learn, embed):
        alice, bob = self.user(), self.user()
        store.save_turn(alice, 'previous', 'My interview is on Friday', 'Good luck')
        store.save_turn(bob, 'previous', 'Another user secret', 'Reply')
        personal_chat.chat(alice, 'new', 'When is my interview?')
        prompt = str(generate.call_args.args[0])
        self.assertIn('My interview is on Friday', prompt)
        self.assertNotIn('Another user secret', prompt)
        personal_chat.chat(alice, 'new', 'What did I just ask?')
        self.assertIn('When is my interview?', str(generate.call_args.args[0]))
        store.set_user(alice, False)
        self.assertEqual(store.conversations(alice), [])
        personal_chat.chat(alice, 'new', 'Hello')
        self.assertNotIn('My interview is on Friday', str(generate.call_args.args[0]))

    def test_streamlit_resume_and_switch_restore_saved_messages(self):
        # The app filename shadows the installed Streamlit package during imports.
        import sys
        original_path = sys.path[:]
        try:
            sys.path = [entry for entry in sys.path if Path(entry or '.').resolve() != Path.cwd()]
            from streamlit.testing.v1 import AppTest
        finally:
            sys.path = original_path
        user = self.user()
        store.save_turn(user, 'older', 'Earlier discussion', 'Earlier reply')
        store.save_turn(user, 'latest', 'Latest discussion', 'Latest reply')

        def request(method, url, **kwargs):
            return self.client.request(method, url.removeprefix('http://localhost:8000'),
                                       headers=kwargs['headers'], **({'json': kwargs['json']} if 'json' in kwargs else {}))

        with patch('requests.request', side_effect=request):
            ui = AppTest.from_file('streamlit.py').run()
            ui.text_input[1].set_value(user)
            next(button for button in ui.button if button.label == 'Resume profile').click().run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.session_state.conversation_id, 'latest')
            self.assertEqual(ui.session_state.messages[0]['content'], 'Latest discussion')
            ui = AppTest.from_file('streamlit.py')
            ui.session_state.user_id = user
            ui.session_state.conversation_id = 'latest'
            ui.session_state.messages = store.history(user, 'latest')
            ui.run()
            ui.selectbox[0].select('older').run()
            next(button for button in ui.button if button.label == 'Open saved conversation').click().run()
            self.assertEqual(ui.session_state.conversation_id, 'older')
            self.assertEqual(ui.session_state.messages[0]['content'], 'Earlier discussion')
            next(button for button in ui.button if button.label == 'New conversation').click().run()
            self.assertEqual(ui.session_state.messages, [])
            self.assertNotIn(ui.session_state.conversation_id, ['older', 'latest'])

    def test_support_prompt_boundaries(self):
        prompt=personal_chat.SYSTEM_PROMPT
        for rule in ('not a licensed therapist', 'Never diagnose', 'immediate safety',
                     'not instructions', 'another user'):
            self.assertIn(rule,prompt)


if __name__ == '__main__':
    unittest.main()
