"""Local development UI; calls the same API used by transport adapters."""
import json
import uuid
import requests
import streamlit as st
from config import Settings

st.set_page_config(page_title='Reflect', page_icon='🌿')
settings = Settings()
st.title('Reflect')
st.caption('An AI companion for emotional support and self-reflection. Not a licensed therapist or emergency service.')
st.caption('Messages are processed by the configured Ollama server. Memory saves your profile and conversation text locally only when you opt in.')


def api(method, path, **kwargs):
    response = requests.request(method, 'http://localhost:8000'+path,
        headers={'x-api-key': settings.API_KEY}, timeout=600, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else None


if 'user_id' not in st.session_state:
    name = st.text_input('What would you like to be called?')
    consent = st.checkbox('Remember my profile and conversations to personalize future chats', value=False)
    if st.button('Start talking'):
        try:
            user = api('POST', '/profiles', json={'memory_consent': consent,
                'profile': {'preferred_name': name}})
            st.session_state.user_id = user['user_id']
            st.session_state.conversation_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.rerun()
        except requests.RequestException:
            st.error('Could not connect to the backend. Start uvicorn app:app on port 8000.')
    resume_id = st.text_input('Or resume a saved profile ID')
    if st.button('Resume profile') and resume_id:
        try:
            user = api('GET', '/profiles/'+resume_id.strip())
            saved = api('GET', '/chat/conversations/'+user['user_id'])['conversations']
            conversation_id = saved[0]['conversation_id'] if saved else str(uuid.uuid4())
            messages = api('GET', '/chat/history/'+user['user_id']+'/'+conversation_id)['messages'] if saved else []
            st.session_state.user_id = user['user_id']
            st.session_state.conversation_id = conversation_id
            st.session_state.messages = messages
            st.rerun()
        except requests.RequestException:
            st.error('Profile not found or backend unavailable.')
    st.stop()

with st.sidebar:
    st.caption('Save this profile ID to resume later:')
    st.code(st.session_state.user_id)
    if st.button('New conversation'):
        st.session_state.conversation_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    try:
        saved = api('GET', '/chat/conversations/'+st.session_state.user_id)['conversations']
        if saved:
            labels = {item['conversation_id']: f"{item['started_at']} · {item['message_count']} messages · {item['conversation_id'][:8]}"
                      for item in saved}
            selected = st.selectbox('Saved conversations', list(labels),
                format_func=lambda value: labels[value], index=None, placeholder='Choose a saved conversation')
            if st.button('Open saved conversation') and selected:
                messages = api('GET', '/chat/history/'+st.session_state.user_id+'/'+selected)['messages']
                st.session_state.conversation_id = selected
                st.session_state.messages = messages
                st.rerun()
        else:
            st.caption('No saved chats yet. Enable memory to save future conversations.')
    except requests.RequestException:
        st.error('Could not load saved conversations.')
    if st.button('View my profile'):
        try:
            st.json(api('GET', '/profiles/'+st.session_state.user_id))
        except requests.RequestException:
            st.error('Could not load your profile.')
    with st.expander('Edit profile or enable memory'):
        profile_json = st.text_area('Profile JSON (use View my profile to inspect the current values)', '{}')
        enable_memory = st.checkbox('Save this profile and future conversations')
        if st.button('Save profile settings'):
            try:
                api('PUT', '/profiles/'+st.session_state.user_id,
                    json={'memory_consent': enable_memory, 'profile': json.loads(profile_json)})
                st.success('Profile settings saved.')
            except (requests.RequestException, ValueError):
                st.error('Could not save. Check the profile JSON and backend connection.')
    if st.button('Turn memory off and erase saved content'):
        try:
            api('PUT', '/profiles/'+st.session_state.user_id, json={'memory_consent': False})
            st.session_state.messages = []
            st.success('Saved profile content, conversations and embeddings erased.')
        except requests.RequestException:
            st.error('Could not update memory settings.')
    if st.button('Delete my profile and all saved chats'):
        try:
            api('DELETE', '/profiles/'+st.session_state.user_id)
            st.session_state.clear()
            st.rerun()
        except requests.RequestException:
            st.error('Could not delete your profile. Please try again.')

for message in st.session_state.messages:
    with st.chat_message(message['role']):
        st.markdown(message['content'])

if text := st.chat_input('What is on your mind?'):
    with st.chat_message('user'):
        st.markdown(text)
    with st.chat_message('assistant'), st.spinner('Reflecting…'):
        try:
            result = api('POST', '/chat/chat', json={'user_id': st.session_state.user_id,
                'conversation_id': st.session_state.conversation_id, 'message': text,
                'transient_history': st.session_state.messages[-20:]})
            st.markdown(result['reply'])
            st.session_state.messages.extend([{'role': 'user', 'content': text},
                                              {'role': 'assistant', 'content': result['reply']}])
        except requests.RequestException:
            st.error('Could not get a reply. Please try again.')
