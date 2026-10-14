"""Meta webhook transport; no outbound request runs until a signed event arrives."""
import hashlib
import hmac
import json
import logging

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from config import Settings
from services import profile_store as store
from services.personal_chat import chat, user_lock

router = APIRouter(prefix='/webhooks/whatsapp')
settings = Settings()
logger = logging.getLogger(__name__)
INTRO = ("I'm Reflect, an AI support companion, not a licensed therapist or emergency service. "
         "Your messages are processed by our configured Ollama server. I can remember your profile and conversations "
         "to personalize future replies if you choose. Reply REMEMBER ON to enable this, "
         "REMEMBER OFF to erase saved memories, or DELETE MY DATA to remove your profile. "
         "Without memory, I respond to each message without saving its text. What's on your mind?")


def valid_signature(body, signature):
    if not settings.WHATSAPP_APP_SECRET or not signature:
        return False
    expected = 'sha256='+hmac.new(settings.WHATSAPP_APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def send_text(recipient, text):
    response = requests.post(
        f'https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages',
        headers={'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}'},
        json={'messaging_product': 'whatsapp', 'to': recipient, 'type': 'text',
              'text': {'body': text[:4096]}}, timeout=30)
    response.raise_for_status()


def process_message(message):
    event_id = message['id']
    sender = message['from']
    user_id = 'whatsapp:'+sender
    text = message['text']['body'].strip()
    try:
        with user_lock(user_id):
            user = store.get_user(user_id)
            command = text.upper()
            if command == 'DELETE MY DATA':
                store.delete_user(user_id)
                reply = 'Your saved profile, conversations and embeddings have been deleted.'
            elif user is None:
                store.set_user(user_id, False)
                reply = INTRO+'\n\n'+chat(user_id, 'whatsapp', text)['reply']
            elif command == 'REMEMBER ON':
                store.set_user(user_id, True, user['profile'])
                reply = 'Memory is on. I will save our conversations and learn a profile from what you share. You can switch it off anytime. What would you like me to know about you?'
            elif command == 'REMEMBER OFF':
                store.set_user(user_id, False)
                reply = 'Memory is off. Your saved profile, conversations and embeddings have been erased.'
            else:
                reply = chat(user_id, 'whatsapp', text)['reply']
            send_text(sender, reply)
            store.finish_event(event_id, 'done')
    except Exception:
        # Never include webhook bodies, phone numbers or personal messages in logs.
        logger.error('WhatsApp message processing failed; check provider configuration')
        store.finish_event(event_id, 'failed')


@router.get('')
def verify(request: Request):
    query = request.query_params
    if (settings.WHATSAPP_VERIFY_TOKEN and query.get('hub.mode') == 'subscribe'
            and hmac.compare_digest(query.get('hub.verify_token', ''), settings.WHATSAPP_VERIFY_TOKEN)):
        return PlainTextResponse(query.get('hub.challenge', ''))
    raise HTTPException(403, 'Invalid verification token')


@router.post('')
async def receive(request: Request, tasks: BackgroundTasks):
    if not all((settings.WHATSAPP_APP_SECRET, settings.WHATSAPP_ACCESS_TOKEN,
                settings.WHATSAPP_PHONE_NUMBER_ID, settings.WHATSAPP_API_VERSION)):
        raise HTTPException(503, 'WhatsApp is not configured')
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(413, 'Payload too large')
    if not valid_signature(body, request.headers.get('x-hub-signature-256')):
        raise HTTPException(403, 'Invalid webhook signature')
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, 'Invalid JSON')
    if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
        raise HTTPException(400, 'Invalid webhook object')
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            if value.get('metadata', {}).get('phone_number_id') != settings.WHATSAPP_PHONE_NUMBER_ID:
                continue
            for message in value.get('messages', []):
                if (message.get('type') == 'text' and message.get('id') and message.get('from')
                        and isinstance(message.get('text', {}).get('body'), str)
                        and message['text']['body'].strip() and len(message['text']['body']) <= 10000):
                    if store.claim_event(message['id']):
                        tasks.add_task(process_message, message)
    return {'status': 'accepted'}
