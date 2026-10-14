"""Local administrator view for the personal-support application."""
import hmac
from contextlib import closing
import streamlit as st
from config import Settings
from database import get_connection
from services import profile_store as store

st.set_page_config(page_title='Reflect Admin', page_icon='🌿')
settings = Settings()
if not st.session_state.get('authenticated'):
    st.title('Reflect Admin')
    username = st.text_input('Username')
    password = st.text_input('Password', type='password')
    if st.button('Sign in'):
        if (hmac.compare_digest(username, settings.ADMIN_USERNAME)
                and hmac.compare_digest(password, settings.ADMIN_PASSWORD)):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error('Incorrect credentials.')
    st.stop()

st.title('Reflect Admin')
st.caption('Local administrator access to saved profiles. Conversation text is not shown here.')
if st.sidebar.button('Sign out'):
    st.session_state.clear()
    st.rerun()
store.initialize()
with closing(get_connection()) as db:
    users = db.execute('SELECT user_id,consent FROM personal_users ORDER BY user_id').fetchall()
    messages = db.execute('SELECT COUNT(*) FROM personal_messages').fetchone()[0]
    memories = db.execute('SELECT COUNT(*) FROM personal_memories').fetchone()[0]
    failed = db.execute("SELECT COUNT(*) FROM whatsapp_events WHERE status='failed'").fetchone()[0]
cols = st.columns(4)
for col, title, count in zip(cols, ['Profiles','Saved messages','Profile vectors','Failed WhatsApp events'],
                             [len(users),messages,memories,failed]):
    col.metric(title, count)
if users:
    user_id = st.selectbox('Inspect a saved profile', [row['user_id'] for row in users])
    if st.button('Show profile'):
        st.json(store.get_user(user_id))
else:
    st.info('No profiles yet. Start the API and chat UI to create one.')
