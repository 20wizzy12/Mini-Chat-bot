import streamlit as st
import sqlite3
import hashlib
import datetime
import os
import json

DB_FILE = "chat_app.db"
DATA_FILE = "chat_data.json"

# ---------------------- DB FUNCTIONS ---------------------- #
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            online INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            msg TEXT NOT NULL,
            time TEXT NOT NULL,
            is_group INTEGER NOT NULL DEFAULT 0
        );""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT UNIQUE NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        );""")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            username TEXT NOT NULL
        );""")

        conn.commit()

# ---------------------- JSON FUNCTIONS ---------------------- #
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"users": {}, "messages": [], "groups": {}}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ---------------------- AUTH FUNCTIONS ---------------------- #
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ---- SQLite ----
def signup_sql(username, password):
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

def login_sql(username, password):
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

def logout_sql(username):
    with get_conn() as conn:
        conn.execute("UPDATE users SET online=0 WHERE username=?", (username,))
        conn.commit()

def get_online_users_sql():
    with get_conn() as conn:
        return [row[0] for row in conn.execute("SELECT username FROM users WHERE online=1").fetchall()]

# ---- JSON ----
def signup_json(username, password):
    data = load_data()
    if username in data["users"]:
        return False
    data["users"][username] = {
        "password_hash": hash_password(password),
        "online": 0,
        "created_at": str(datetime.datetime.now())
    }
    save_data(data)
    return True

def login_json(username, password):
    data = load_data()
    user = data["users"].get(username)
    if user and user["password_hash"] == hash_password(password):
        data["users"][username]["online"] = 1
        save_data(data)
        return True
    return False

def logout_json(username):
    data = load_data()
    if username in data["users"]:
        data["users"][username]["online"] = 0
        save_data(data)

def get_online_users_json():
    data = load_data()
    return [u for u, info in data["users"].items() if info["online"] == 1]

# ---------------------- CHAT FUNCTIONS ---------------------- #
# ---- SQLite ----
def send_message_sql(sender, receiver, msg, is_group=0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (sender, receiver, msg, time, is_group) VALUES (?, ?, ?, ?, ?)",
            (sender, receiver, msg, str(datetime.datetime.now()), is_group)
        )
        conn.commit()

def get_conversation_sql(a, b, is_group=0):
    with get_conn() as conn:
        if is_group:
            rows = conn.execute(
                "SELECT sender, msg, time FROM messages WHERE is_group=1 AND receiver=? ORDER BY id ASC",
                (b,)
            ).fetchall()
            return rows
        else:
            rows = conn.execute(
                "SELECT sender, receiver, msg, time FROM messages WHERE is_group=0 AND ((sender=? AND receiver=?) OR (sender=? AND receiver=?)) ORDER BY id ASC",
                (a, b, b, a)
            ).fetchall()
            return rows

# ---- JSON ----
def send_message_json(sender, receiver, msg, is_group=0):
    data = load_data()
    data["messages"].append({
        "sender": sender,
        "receiver": receiver,
        "msg": msg,
        "time": str(datetime.datetime.now()),
        "is_group": is_group
    })
    save_data(data)

def get_conversation_json(a, b, is_group=0):
    data = load_data()
    if is_group:
        return [(m["sender"], m["msg"], m["time"]) for m in data["messages"] if m["is_group"] == 1 and m["receiver"] == b]
    else:
        return [(m["sender"], m["receiver"], m["msg"], m["time"]) for m in data["messages"]
                if m["is_group"] == 0 and (
                    (m["sender"] == a and m["receiver"] == b) or
                    (m["sender"] == b and m["receiver"] == a)
                )]

# ---------------------- GROUP FUNCTIONS ---------------------- #
# ---- SQLite ----
def create_group_sql(group_name, created_by):
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

def add_member_sql(group_name, username):
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

def get_user_groups_sql(username):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT g.group_name FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.username=?;
        """, (username,)).fetchall()
        return [r[0] for r in rows]

# ---- JSON ----
def create_group_json(group_name, created_by):
    data = load_data()
    if group_name in data["groups"]:
        return False
    data["groups"][group_name] = {
        "created_by": created_by,
        "created_at": str(datetime.datetime.now()),
        "members": [created_by]
    }
    save_data(data)
    return True

def add_member_json(group_name, username):
    data = load_data()
    if group_name in data["groups"]:
        if username not in data["groups"][group_name]["members"]:
            data["groups"][group_name]["members"].append(username)
            save_data(data)
            return True
    return False

def get_user_groups_json(username):
    data = load_data()
    return [g for g, info in data["groups"].items() if username in info["members"]]

# ---------------------- STREAMLIT APP ---------------------- #
st.set_page_config(page_title="💬 Wizzy Chat", page_icon="💬", layout="centered")
init_db()

if "user" not in st.session_state:
    st.session_state.user = None
if "backend" not in st.session_state:
    st.session_state.backend = "SQLite"

# Sidebar toggle
st.sidebar.title("⚙️ Settings")
st.session_state.backend = st.sidebar.radio("Storage Backend", ["SQLite", "JSON"])

backend = st.session_state.backend

# ---------------------- LOGIN / SIGNUP ---------------------- #
if st.session_state.user is None:
    st.title("🔑 Login / Sign Up")

    choice = st.radio("Choose:", ["Login", "Sign Up"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if choice == "Sign Up":
        if st.button("Sign Up"):
            success = signup_sql(username, password) if backend == "SQLite" else signup_json(username, password)
            if success:
                st.success("Account created. Please login!")
            else:
                st.error("Username already taken!")
    else:
        if st.button("Login"):
            success = login_sql(username, password) if backend == "SQLite" else login_json(username, password)
            if success:
                st.session_state.user = username
                st.rerun()
            else:
                st.error("Invalid username/password.")

else:
    st.sidebar.title(f"Welcome {st.session_state.user} 👋")
    if st.sidebar.button("Logout"):
        if backend == "SQLite":
            logout_sql(st.session_state.user)
        else:
            logout_json(st.session_state.user)
        st.session_state.user = None
        st.rerun()

    online_users = get_online_users_sql() if backend == "SQLite" else get_online_users_json()
    st.sidebar.subheader("🟢 Online Users")
    for u in online_users:
        if u != st.session_state.user:
            st.sidebar.write(u)

    my_groups = get_user_groups_sql(st.session_state.user) if backend == "SQLite" else get_user_groups_json(st.session_state.user)
    st.sidebar.subheader("👥 Groups")
    for g in my_groups:
        st.sidebar.write(f"📌 {g}")

    # Chat area
    chat_mode = st.radio("Chat Mode", ["Private Chat", "Group Chat"])

    if chat_mode == "Private Chat":
        chat_with = st.selectbox("Select a user", [u for u in online_users if u != st.session_state.user])
        if chat_with:
            history = get_conversation_sql(st.session_state.user, chat_with) if backend == "SQLite" else get_conversation_json(st.session_state.user, chat_with)
            st.subheader(f"Chat with {chat_with}")
            for sender, receiver, msg, time in history:
                align = "➡️" if sender == st.session_state.user else "⬅️"
                st.write(f"{align} **{sender}**: {msg} ({time})")

            new_msg = st.text_input("Type a message...")
            if st.button("Send"):
                if new_msg.strip():
                    if backend == "SQLite":
                        send_message_sql(st.session_state.user, chat_with, new_msg)
                    else:
                        send_message_json(st.session_state.user, chat_with, new_msg)
                    st.rerun()

    else:  # Group Chat
        group_action = st.radio("Choose:", ["Join Group", "Create Group"])

        if group_action == "Create Group":
            group_name = st.text_input("Group Name")
            if st.button("Create Group"):
                created = create_group_sql(group_name, st.session_state.user) if backend == "SQLite" else create_group_json(group_name, st.session_state.user)
                if created:
                    if backend == "SQLite":
                        add_member_sql(group_name, st.session_state.user)
                    else:
                        add_member_json(group_name, st.session_state.user)
                    st.success(f"Group '{group_name}' created!")
                else:
                    st.error("Group already exists!")
        else:
            group_list = get_user_groups_sql(st.session_state.user) if backend == "SQLite" else get_user_groups_json(st.session_state.user)
            group_choice = st.selectbox("Select Group", group_list)
            if group_choice:
                history = get_conversation_sql(st.session_state.user, group_choice, is_group=1) if backend == "SQLite" else get_conversation_json(st.session_state.user, group_choice, is_group=1)
                st.subheader(f"Group Chat: {group_choice}")
                for sender, msg, time in history:
                    align = "➡️" if sender == st.session_state.user else "⬅️"
                    st.write(f"{align} **{sender}**: {msg} ({time})")

                new_msg = st.text_input("Type a message...")
                if st.button("Send"):
                    if new_msg.strip():
                        if backend == "SQLite":
                            send_message_sql(st.session_state.user, group_choice, new_msg, is_group=1)
                        else:
                            send_message_json(st.session_state.user, group_choice, new_msg, is_group=1)
                        st.rerun()
