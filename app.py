"""Personal support bot API with a transport-independent conversation core."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from routers import personal_router, whatsapp_router, health_check_router
from services import profile_store
from services.chat_model import get_chat_client


@asynccontextmanager
async def lifespan(app):
    profile_store.initialize()
    yield


app = FastAPI(title='Reflect — Personal Support Bot',
    description='Opt-in user profiles, embedded memories, and supportive AI conversations.',
    version='2.0.0', lifespan=lifespan)
app.include_router(personal_router.router, tags=['Profiles and conversations'])
app.include_router(whatsapp_router.router, tags=['Meta WhatsApp'])
app.include_router(health_check_router.router, tags=['Optional infrastructure'])


@app.get('/')
def root():
    return {'service': 'Reflect', 'version': '2.0.0', 'docs': '/docs',
            'disclosure': 'AI support companion; not a licensed therapist or emergency service.'}


@app.get('/health')
def health():
    return get_chat_client().health()
