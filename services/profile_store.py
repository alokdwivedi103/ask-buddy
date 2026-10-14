"""User-scoped profiles, conversation history, and vector memories for a local instance."""
import hashlib
import json
import math
from contextlib import closing

from database import get_connection
from config import Settings

settings = Settings()


def initialize():
    with closing(get_connection()) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS personal_users (
            user_id TEXT PRIMARY KEY, consent INTEGER NOT NULL DEFAULT 0,
            profile TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS personal_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS personal_history ON personal_messages(user_id, conversation_id, id);
        CREATE TABLE IF NOT EXISTS personal_memories (
            user_id TEXT NOT NULL, memory_id TEXT NOT NULL, content TEXT NOT NULL,
            embedding TEXT NOT NULL, PRIMARY KEY(user_id, memory_id));
        CREATE TABLE IF NOT EXISTS whatsapp_events (
            event_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending');
        ''')


def get_user(user_id):
    with closing(get_connection()) as db:
        row = db.execute('SELECT * FROM personal_users WHERE user_id=?', (user_id,)).fetchone()
    return {'user_id': user_id, 'memory_consent': bool(row['consent']),
            'profile': json.loads(row['profile'])} if row else None


def set_user(user_id, consent, profile=None):
    with closing(get_connection()) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute('INSERT OR IGNORE INTO personal_users(user_id) VALUES (?)', (user_id,))
        db.execute('UPDATE personal_users SET consent=? WHERE user_id=?', (int(consent), user_id))
        if not consent:
            db.execute('DELETE FROM personal_messages WHERE user_id=?', (user_id,))
            db.execute('DELETE FROM personal_memories WHERE user_id=?', (user_id,))
            db.execute("UPDATE personal_users SET profile='{}' WHERE user_id=?", (user_id,))
        elif profile is not None:
            db.execute('UPDATE personal_users SET profile=? WHERE user_id=?', (json.dumps(profile), user_id))
        db.commit()
    return get_user(user_id)


def conversations(user_id):
    with closing(get_connection()) as db:
        rows = db.execute("""SELECT conversation_id, MIN(created_at) AS started_at,
            MAX(created_at) AS updated_at, COUNT(*) AS message_count
            FROM personal_messages WHERE user_id=? GROUP BY conversation_id
            ORDER BY MAX(id) DESC""", (user_id,)).fetchall()
    return [dict(row) for row in rows]


def previous_history(user_id, conversation_id, limit=20):
    with closing(get_connection()) as db:
        rows = db.execute("""SELECT conversation_id, role, content FROM personal_messages
            WHERE user_id=? AND conversation_id<>? ORDER BY id DESC LIMIT ?""",
            (user_id, conversation_id, limit)).fetchall()
    return [dict(row) for row in reversed(rows)]


def history(user_id, conversation_id, limit=20):
    with closing(get_connection()) as db:
        query = 'SELECT role,content FROM personal_messages WHERE user_id=? AND conversation_id=? ORDER BY id DESC'
        params = (user_id, conversation_id)
        if limit is not None:
            query += ' LIMIT ?'
            params += (limit,)
        rows = db.execute(query, params).fetchall()
    return [dict(row) for row in reversed(rows)]


def save_turn(user_id, conversation_id, user_text, reply):
    with closing(get_connection()) as db:
        db.execute("BEGIN IMMEDIATE")
        db.executemany('INSERT INTO personal_messages(user_id,conversation_id,role,content) VALUES (?,?,?,?)',
                       [(user_id, conversation_id, 'user', user_text), (user_id, conversation_id, 'assistant', reply)])
        db.commit()


def save_memory(user_id, content, vector, memory_id=None):
    memory_id = memory_id or hashlib.sha256(content.encode()).hexdigest()
    with closing(get_connection()) as db:
        db.execute('INSERT OR REPLACE INTO personal_memories VALUES (?,?,?,?)',
                   (user_id, memory_id, content, json.dumps({'model': settings.OLLAMA_EMBED_MODEL, 'vector': vector})))


def relevant_memories(user_id, vector, limit=4):
    if not vector or not any(vector):
        return []
    with closing(get_connection()) as db:
        rows = db.execute('SELECT content,embedding FROM personal_memories WHERE user_id=?',
                          (user_id,)).fetchall()
    ranked = []
    norm = math.sqrt(sum(v*v for v in vector))
    for row in rows:
        stored = json.loads(row['embedding'])
        # Legacy Google vectors and vectors from another model are incompatible.
        if not isinstance(stored, dict) or stored.get('model') != settings.OLLAMA_EMBED_MODEL:
            continue
        candidate = stored['vector']
        other_norm = math.sqrt(sum(v*v for v in candidate))
        if len(candidate) == len(vector) and other_norm:
            score = sum(a*b for a,b in zip(vector, candidate))/(norm*other_norm)
            if score > 0.3:
                ranked.append((score, row['content']))
    return [content for _,content in sorted(ranked, reverse=True)[:limit]]


def delete_user(user_id):
    with closing(get_connection()) as db:
        db.execute("BEGIN IMMEDIATE")
        for table in ('personal_messages', 'personal_memories', 'personal_users'):
            db.execute(f'DELETE FROM {table} WHERE user_id=?', (user_id,))
        db.commit()


def claim_event(event_id):
    with closing(get_connection()) as db:
        cursor = db.execute("INSERT OR IGNORE INTO whatsapp_events(event_id) VALUES (?)", (event_id,))
    return cursor.rowcount == 1


def finish_event(event_id, status):
    with closing(get_connection()) as db:
        db.execute('UPDATE whatsapp_events SET status=? WHERE event_id=?', (status, event_id))


def clear_memories(user_id):
    with closing(get_connection()) as db:
        db.execute('DELETE FROM personal_memories WHERE user_id=?', (user_id,))
