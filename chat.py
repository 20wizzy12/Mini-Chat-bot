import streamlit as st
import sqlite3
import hashlib
import datetime
from contextlib import contextmanager

# Optional: pip install streamlit-autorefresh
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOR = True
except Exception:
    AUTOR = False

DB_FILE = "chat.db"

# -------------------------
# DB Utilities
# -------------------------
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        # Improve concurrency
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        # Users table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            online INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """)
        # Messages table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            msg TEXT NOT NULL,
            time TEXT NOT NULL
        );
        """)
        # Indexes for speed
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_pair_time ON messages(sender, receiver, time);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_time ON messages(time);")
        conn.commit()

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username: str, password: str) -> tuple[bool, str]:
    if not username or not password:
        return False, "Username and password are required."
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
                (username, hash_pw(password), datetime.datetime.utcnow().isoformat())
            )
            conn.commit()
            return True, "Account created! Please login."
        except sqlite3.IntegrityError:
            return False, "Username already exists."

def authenticate(username: str, password: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if not row:
            return False
        return row["password_hash"] == hash_pw(password)

def set_online(username: str, online: bool):
    with get_conn() as conn:
        conn.execute("UPDATE users SET online = ? WHERE username = ?", (1 if online else 0, username))
        conn.commit()

def get_online_users(exclude_username: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username FROM users WHERE online = 1 AND username != ? ORDER BY username COLLATE NOCASE",
            (exclude_username,)
        ).fetchall()
        return [r["username"] for r in rows]

def send_message(sender: str, receiver: str, msg: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (sender, receiver, msg, time) VALUES (?,?,?,?)",
            (sender, receiver, msg, datetime.datetime.now().strftime("%H:%M"))
        )
        conn.commit()

def get_conversation(a: str, b: str):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT sender, receiver, msg, time
            FROM messages
            WHERE (sender = ? AND receiver = ?)
               OR (sender = ? AND receiver = ?)
            ORDER BY id ASC
            """,
            (a, b, b, a)
        ).fetchall()
        return [dict(r) for r in rows]

def user_exists(username: str) -> bool:
    with get_conn() as conn:
        r = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        return bool(r)

# -------------------------
# App UI
# -------------------------
st.set_page_config(page_title="💬 Wizzy Chat (SQLite)", page_icon="💬", layout="centered")
init_db()

st.title("💬 Wizzy Username-to-Username Chat (SQLite Edition)")

# CSS
st.markdown("""
    <style>
    .chat-container {
        height: 420px;
        overflow-y: scroll;
        border: 1px solid #ccc;
        border-radius: 10px;
        padding: 10px;
        background-color: #f9f9f9;
    }
    .chat-bubble {
        max-width: 70%;
        padding: 10px 15px;
        border-radius: 20px;
        margin: 5px;
        font-size: 15px;
        line-height: 1.4;
        display: inline-block;
        word-wrap: break-word;
    }
    .you {
        background-color: #DCF8C6;
        color: black;
        margin-left: auto;
        display: block;
        text-align: right;
    }
    .them {
        background-color: #EAEAEA;
        color: black;
        margin-right: auto;
        display: block;
        text-align: left;
    }
    .timestamp {
        font-size: 11px;
        color: gray;
        margin-top: 3px;
        display: block;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar auth
st.sidebar.header("🔑 Account")
menu = st.sidebar.radio("Menu", ["Login", "Sign Up"])

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None

if menu == "Sign Up":
    st.sidebar.subheader("Create Account")
    new_user = st.sidebar.text_input("Username", max_chars=15, key="su_user")
    new_password = st.sidebar.text_input("Password", type="password", key="su_pass")
    if st.sidebar.button("Sign Up"):
        ok, msg = create_user(new_user.strip(), new_password)
        (st.sidebar.success if ok else st.sidebar.error)(msg)

elif menu == "Login":
    st.sidebar.subheader("Login")
    username = st.sidebar.text_input("Username", max_chars=15, key="li_user")
    password = st.sidebar.text_input("Password", type="password", key="li_pass")
    if st.sidebar.button("Login"):
        if authenticate(username.strip(), password):
            # Force toggle online (handles double-login)
            set_online(username.strip(), False)
            st.session_state.logged_in = True
            st.session_state.username = username.strip()
            set_online(st.session_state.username, True)
            st.sidebar.success("✅ Logged in!")
        else:
            st.sidebar.error("❌ Invalid credentials!")

# Chat UI
if st.session_state.logged_in:
    me = st.session_state.username
    st.success(f"Logged in as {me}")

    st.sidebar.subheader("🟢 Online Users")
    online_users = get_online_users(me)
    if online_users:
        chat_with = st.sidebar.selectbox("Select user to chat with:", online_users)
    else:
        chat_with = None
        st.sidebar.info("No one else is online 😢")

    if chat_with:
        st.subheader(f"Chat between {me} and {chat_with}")

        # Auto refresh every 3s
        if AUTOR:
            st_autorefresh(interval=3000, key="refresh")
        else:
            st.caption("Hint: Install `streamlit-autorefresh` for live updates.")

        chat_box = st.empty()

        # Send form
        with st.form("send_message", clear_on_submit=True):
            msg = st.text_input("Your message:")
            send = st.form_submit_button("Send")
            if send and msg.strip():
                send_message(me, chat_with, msg.strip())

        # Render conversation
        history = get_conversation(me, chat_with)

        with chat_box.container():
            st.markdown("<div class='chat-container'>", unsafe_allow_html=True)

            if not history:
                st.info("No messages yet. Say hi 👋")

            for chat in history:
                if chat["sender"] == me:
                    st.markdown(
                        f"<div class='chat-bubble you'>{chat['msg']}<span class='timestamp'>{chat['time']}</span></div>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"<div class='chat-bubble them'>{chat['msg']}<span class='timestamp'>{chat['time']}</span></div>",
                        unsafe_allow_html=True
                    )

            st.markdown("</div>", unsafe_allow_html=True)

            # Auto-scroll
            st.markdown("""
                <script>
                    var chatContainer = window.parent.document.querySelector('.chat-container');
                    if(chatContainer) {
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }
                </script>
            """, unsafe_allow_html=True)

    # Logout
    if st.button("🚪 Logout"):
        set_online(me, False)
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()
