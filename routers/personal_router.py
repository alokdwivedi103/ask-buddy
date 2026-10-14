import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import verify_api_key
from services import profile_store as store
from services.personal_chat import Profile, chat, user_lock, embed
import json

router = APIRouter(dependencies=[Depends(verify_api_key)])


class UserCreate(BaseModel):
    memory_consent: bool = False
    profile: Profile = Field(default_factory=Profile)


class ProfileUpdate(UserCreate):
    pass


class ContextMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=10000)


class ChatMessage(BaseModel):
    user_id: str = Field(min_length=1, max_length=150)
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=150)
    message: str = Field(min_length=1, max_length=10000)
    transient_history: list[ContextMessage] = Field(default_factory=list, max_length=20)


def require_user(user_id):
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(404, 'User not found')
    return user


@router.post('/profiles', status_code=201)
def create_profile(body: UserCreate):
    user_id = 'web:'+str(uuid.uuid4())
    return store.set_user(user_id, body.memory_consent, body.profile.model_dump())


@router.get('/profiles/{user_id}')
def read_profile(user_id: str):
    return require_user(user_id)


@router.put('/profiles/{user_id}')
def update_profile(user_id: str, body: ProfileUpdate):
    with user_lock(user_id):
        require_user(user_id)
        result = store.set_user(user_id, body.memory_consent, body.profile.model_dump())
        if body.memory_consent:
            text = json.dumps(result['profile'])
            vector = embed(text, 'RETRIEVAL_DOCUMENT')
            # Remove the previous vector even if re-embedding is temporarily unavailable.
            store.clear_memories(user_id)
            if vector:
                store.save_memory(user_id, text, vector, 'profile')
        return result


@router.delete('/profiles/{user_id}', status_code=204)
def remove_profile(user_id: str):
    with user_lock(user_id):
        require_user(user_id)
        store.delete_user(user_id)


@router.get('/chat/conversations/{user_id}')
def list_conversations(user_id: str):
    require_user(user_id)
    return {'conversations': store.conversations(user_id)}


@router.get('/chat/history/{user_id}/{conversation_id}')
def read_history(user_id: str, conversation_id: str):
    require_user(user_id)
    return {'messages': store.history(user_id, conversation_id, limit=None)}


@router.post('/chat/chat')
def send_message(body: ChatMessage):
    require_user(body.user_id)
    if not body.message.strip():
        raise HTTPException(422, 'Message cannot be blank')
    try:
        return chat(body.user_id, body.conversation_id, body.message,
                    [m.model_dump() for m in body.transient_history])
    except KeyError:
        raise HTTPException(404, 'User not found')
    except Exception:
        raise HTTPException(503, 'The AI service is temporarily unavailable. Please try again.')
