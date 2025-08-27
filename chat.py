import streamlit as st
import sqlite3
import hashlib
import datetime
import os

DB_FILE = "chat_app.db"

# ---------------------- DB FUNCTIONS ---------------------- #
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        # Users table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            online INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );""")

        # Messages table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            msg TEXT NOT NULL,
            time TEXT NOT NULL,
            is_group INTEGER NOT NULL DEFAULT 0
        );""")

        # Groups table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT UNIQUE NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );""")

        # Group members table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            username TEXT NOT NULL
        );""")

        # ✅ Migration check for missing is_group column
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN is_group INTEGER NOT NULL DEFAULT 0;")
        except sqlite3.OperationalError:
            pass

        conn.commit()

# ---------------------- AUTH FUNCTIONS ---------------------- #
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def signup(username, password):
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(password), str(datetime.datetime.now()))
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def login(username, password):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username=? AND password_hash=?",
            (username, hash_password(password))
        ).fetchone()
        if row:
            conn.execute("UPDATE users SET online=1 WHERE username=?", (username,))
            conn.commit()
            return True
    return False

def logout(username):
    with get_conn() as conn:
        conn.execute("UPDATE users SET online=0 WHERE username=?", (username,))
        conn.commit()

def get_online_users():
    with get_conn() as conn:
        return [row[0] for row in conn.execute("SELECT username FROM users WHERE online=1").fetchall()]

# ---------------------- CHAT FUNCTIONS ---------------------- #
def send_message(sender, receiver, msg, is_group=0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (sender, receiver, msg, time, is_group) VALUES (?, ?, ?, ?, ?)",
            (sender, receiver, msg, str(datetime.datetime.now()), is_group)
        )
        conn.commit()

def get_conversation(a, b, is_group=0):
    with get_conn() as conn:
        if is_group:
            rows = conn.execute(
                "SELECT sender, msg, time FROM messages WHERE is_group=1 AND receiver=? ORDER BY id ASC",
                (b,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT sender, receiver, msg, time FROM messages WHERE is_group=0 AND ((sender=? AND receiver=?) OR (sender=? AND receiver=?)) ORDER BY id ASC",
                (a, b, b, a)
            ).fetchall()
        return rows

# ---------------------- GROUP FUNCTIONS ---------------------- #
def create_group(group_name, created_by):
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO groups (group_name, created_by, created_at) VALUES (?, ?, ?)",
                (group_name, created_by, str(datetime.datetime.now()))
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def add_member(group_name, username):
    with get_conn() as conn:
        group_id = conn.execute("SELECT id FROM groups WHERE group_name=?", (group_name,)).fetchone()
        if group_id:
            conn.execute(
                "INSERT INTO group_members (group_id, username) VALUES (?, ?)",
                (group_id[0], username)
            )
            conn.commit()
            return True
        return False

def get_user_groups(username):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT g.group_name FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.username=?;
        """, (username,)).fetchall()
        return [r[0] for r in rows]

# ---------------------- STREAMLIT APP ---------------------- #
st.set_page_config(page_title="💬 Wizzy Chat", page_icon="💬", layout="centered")
init_db()

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🔑 Login / Sign Up")

    choice = st.radio("Choose:", ["Login", "Sign Up"])

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if choice == "Sign Up":
        if st.button("Sign Up"):
            if signup(username, password):
                st.success("Account created. Please login!")
            else:
                st.error("Username already taken!")
    else:
        if st.button("Login"):
            if login(username, password):
                st.session_state.user = username
                st.rerun()
            else:
                st.error("Invalid username/password.")

else:
    st.sidebar.title(f"Welcome {st.session_state.user} 👋")
    if st.sidebar.button("Logout"):
        logout(st.session_state.user)
        st.session_state.user = None
        st.rerun()

    online_users = get_online_users()
    st.sidebar.subheader("🟢 Online Users")
    for u in online_users:
        if u != st.session_state.user:
            st.sidebar.write(u)

    st.sidebar.subheader("👥 Groups")
    my_groups = get_user_groups(st.session_state.user)
    for g in my_groups:
        st.sidebar.write(f"📌 {g}")

    # Chat area
    chat_mode = st.radio("Chat Mode", ["Private Chat", "Group Chat"])

    if chat_mode == "Private Chat":
        chat_with = st.selectbox("Select a user", [u for u in online_users if u != st.session_state.user])
        if chat_with:
            history = get_conversation(st.session_state.user, chat_with)
            st.subheader(f"Chat with {chat_with}")
            for sender, receiver, msg, time in history:
                align = "➡️" if sender == st.session_state.user else "⬅️"
                st.write(f"{align} **{sender}**: {msg} ({time})")

            new_msg = st.text_input("Type a message...")
            if st.button("Send"):
                if new_msg.strip():
                    send_message(st.session_state.user, chat_with, new_msg)
                    st.rerun()

    else:  # Group Chat
        group_action = st.radio("Choose:", ["Join Group", "Create Group"])

        if group_action == "Create Group":
            group_name = st.text_input("Group Name")
            if st.button("Create Group"):
                if create_group(group_name, st.session_state.user):
                    add_member(group_name, st.session_state.user)
                    st.success(f"Group '{group_name}' created!")
                else:
                    st.error("Group already exists!")
        else:
            group_list = get_user_groups(st.session_state.user)
            group_choice = st.selectbox("Select Group", group_list)
            if group_choice:
                history = get_conversation(st.session_state.user, group_choice, is_group=1)
                st.subheader(f"Group Chat: {group_choice}")
                for sender, msg, time in history:
                    align = "➡️" if sender == st.session_state.user else "⬅️"
                    st.write(f"{align} **{sender}**: {msg} ({time})")

                new_msg = st.text_input("Type a message...")
                if st.button("Send"):
                    if new_msg.strip():
                        send_message(st.session_state.user, group_choice, new_msg, is_group=1)
                        st.rerun()
