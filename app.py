"""Julian's Sherlock Mind Palace — Streamlit edition.

A private, local-first visual memory palace. Memories are organised into
nine wings (Grand Hall, Worlds, People & Life, Academic Library,
Professional Office, Health Observatory, Legal & Finance Vault, Cabinet of
Curiosities, Recall Mode) and stored in a local SQLite database
(``palace.db``) next to this file. Nothing leaves this machine.

This is a Streamlit recreation of Julian's original palace (a Python
stdlib HTTP server with a cinematic investigative interface). The wings,
instruments, and three layers are carried over and improved:

- Immutable raw archive: every memory is stored verbatim with its
  creation time and is never edited in place.
- Organised memory: wings, rooms, tags, search, timeline, deduction
  board.
- User-confirmed canon: Canon Vault cards stay fogged (proposed) until
  Julian confirms them; conflicting versions raise an alarm.

Instruments: Deduction Board, Timeline Corridor, Daily Observation
Ritual, Memory Decay (visual fading only — nothing is ever deleted),
Privacy Doors (sensitive wings blurred until deliberately revealed),
Pocket Notebook, Canon Vault, Recall Mode.

Seeded with nothing: an empty palace stays empty until Julian fills it.
"""

import html
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "palace.db"
DECAY_DAYS = 240  # memories unrecalled longer than this visibly fade

WINGS = {
    "Grand Hall": {
        "icon": "\u2302",
        "description": "Universal search and recent case files — the entrance to everything.",
        "accent": "#b99659",
        "rooms": ["Front Desk", "Recent Case Files", "Universal Search"],
        "private": False,
    },
    "Worlds": {
        "icon": "\u25c7",
        "description": "Fictional universes, lore, characters, timelines, and canon.",
        "accent": "#58a6ff",
        "rooms": ["Lore", "Characters", "Timelines", "Canon"],
        "private": False,
    },
    "People & Life": {
        "icon": "\u2659",
        "description": "Relationships, personal history, identity, and reflections.",
        "accent": "#7ee787",
        "rooms": ["Inner Circle", "Family", "Reflections", "Identity", "Daily Observations"],
        "private": False,
    },
    "Academic Library": {
        "icon": "\u2318",
        "description": "Coursework, research, and writing — the shelves of study.",
        "accent": "#d2a8ff",
        "rooms": ["Coursework", "Research", "Writing"],
        "private": False,
    },
    "Professional Office": {
        "icon": "\u25a4",
        "description": "Work, leadership, correspondence, and career material.",
        "accent": "#e8b64c",
        "rooms": ["Leadership", "Correspondence", "Career"],
        "private": False,
    },
    "Health Observatory": {
        "icon": "\u25c9",
        "description": "Private health discussions — kept behind a privacy door.",
        "accent": "#ff7b72",
        "rooms": ["Health Notes", "Appointments"],
        "private": True,
    },
    "Legal & Finance Vault": {
        "icon": "\u25a3",
        "description": "Private legal, financial, housing, and insurance material.",
        "accent": "#ffa657",
        "rooms": ["Legal", "Finance", "Housing", "Insurance"],
        "private": True,
    },
    "Cabinet of Curiosities": {
        "icon": "\u2726",
        "description": "Facts, recipes, questions, and discoveries worth keeping.",
        "accent": "#79c0ff",
        "rooms": ["Facts", "Recipes", "Questions", "Discoveries"],
        "private": False,
    },
}

STORAGE_WINGS = list(WINGS.keys())
PRIVATE_WINGS = {w for w, info in WINGS.items() if info["private"]}

RITUAL_PROMPTS = [
    "What did you notice today that others may have missed?",
    "What decision must your future self understand?",
    "Who mattered today, and why?",
    "What changed in one of your worlds?",
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wing TEXT NOT NULL,
            room TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_recalled TEXT,
            recall_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS recall_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER REFERENCES memories(id),
            remembered INTEGER NOT NULL,
            recalled_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pocket_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            placed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS canon_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER REFERENCES memories(id),
            wing TEXT NOT NULL,
            room TEXT NOT NULL,
            subject TEXT NOT NULL,
            fact TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_wing ON memories(wing, created_at);
        CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)")}
    if "last_recalled" not in columns:
        connection.execute("ALTER TABLE memories ADD COLUMN last_recalled TEXT")
    if "recall_count" not in columns:
        connection.execute("ALTER TABLE memories ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0")
    connection.commit()
    return connection


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_tags(raw: str) -> list:
    return [t.strip() for t in (raw or "").split(",") if t.strip()]


def normalise_tags(raw: str) -> str:
    return ", ".join(parse_tags(raw))


def add_memory(wing: str, room: str, title: str, content: str, tags: str) -> int:
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO memories (wing, room, title, content, tags, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (wing, room, title.strip(), content.strip(), normalise_tags(tags), now_iso()),
        )
        db.commit()
        return cursor.lastrowid


def list_memories(wing=None, room=None, query=None):
    clauses, values = [], []
    if wing:
        clauses.append("wing = ?")
        values.append(wing)
    if room:
        clauses.append("room = ?")
        values.append(room)
    if query:
        like = f"%{query}%"
        clauses.append("(title LIKE ? OR content LIKE ? OR tags LIKE ? OR wing LIKE ? OR room LIKE ?)")
        values.extend((like, like, like, like, like))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as db:
        return [dict(r) for r in db.execute(
            f"SELECT * FROM memories{where} ORDER BY created_at DESC", values
        ).fetchall()]


def get_memory(memory_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return dict(row) if row else None


def delete_memory(memory_id: int) -> None:
    with connect() as db:
        db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        db.execute("DELETE FROM recall_log WHERE memory_id = ?", (memory_id,))
        db.commit()


def touch_memory(memory_id: int) -> None:
    """Mark a memory recalled now (used by a revisit, not a quiz round)."""
    with connect() as db:
        db.execute(
            "UPDATE memories SET last_recalled = ?, recall_count = recall_count + 1 WHERE id = ?",
            (now_iso(), memory_id),
        )
        db.commit()


def log_recall(memory_id: int, remembered: bool) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO recall_log (memory_id, remembered, recalled_at) VALUES (?, ?, ?)",
            (memory_id, 1 if remembered else 0, now_iso()),
        )
        db.execute(
            "UPDATE memories SET last_recalled = ?, recall_count = recall_count + 1 WHERE id = ?",
            (now_iso(), memory_id),
        )
        db.commit()


def wing_counts() -> dict:
    with connect() as db:
        rows = db.execute("SELECT wing, COUNT(*) c FROM memories GROUP BY wing").fetchall()
    return {r["wing"]: r["c"] for r in rows}


def total_memories() -> int:
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]


def total_recall_rounds() -> int:
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM recall_log").fetchone()[0]


def total_tags() -> int:
    tags = set()
    for mem in list_memories():
        tags.update(parse_tags(mem["tags"]))
    return len(tags)


def days_since(iso_text):
    if not iso_text:
        return None
    try:
        then = datetime.fromisoformat(iso_text)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).days


def is_faded(mem: dict) -> bool:
    """A memory fades when it has not been recalled for DECAY_DAYS.

    Fading is visual only — nothing is ever deleted.
    """
    anchor = mem.get("last_recalled") or mem.get("created_at")
    age = days_since(anchor)
    return age is not None and age > DECAY_DAYS


def faded_memories():
    return [m for m in list_memories() if is_faded(m)]


def ritual_done_today() -> bool:
    with connect() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM memories WHERE tags LIKE '%daily-ritual%'"
            " AND date(created_at) = date('now')"
        ).fetchone()[0]
    return count > 0


def add_pocket_note(text: str) -> int:
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO pocket_notes (text, created_at) VALUES (?, ?)", (text.strip(), now_iso())
        )
        db.commit()
        return cursor.lastrowid


def list_pocket_notes(placed: int):
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM pocket_notes WHERE placed = ? ORDER BY created_at DESC", (placed,)
        ).fetchall()]


def place_pocket_note(note_id: int, wing: str, room: str, title: str) -> int:
    with connect() as db:
        note = db.execute("SELECT * FROM pocket_notes WHERE id = ?", (note_id,)).fetchone()
        if note is None:
            return None
        cursor = db.execute(
            "INSERT INTO memories (wing, room, title, content, tags, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (wing, room, title.strip(), note["text"], "pocket-notebook", now_iso()),
        )
        db.execute("UPDATE pocket_notes SET placed = 1 WHERE id = ?", (note_id,))
        db.commit()
        return cursor.lastrowid


def add_canon_card(memory_id, wing, room, subject, fact, status="proposed") -> int:
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO canon_cards (memory_id, wing, room, subject, fact, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (memory_id, wing, room, subject, fact, status, now_iso()),
        )
        db.commit()
        return cursor.lastrowid


def list_canon_cards():
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM canon_cards ORDER BY created_at DESC"
        ).fetchall()]


def canon_contradictions():
    with connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT lower(subject) AS subject, COUNT(DISTINCT fact) AS versions,"
            " GROUP_CONCAT(DISTINCT fact) AS facts FROM canon_cards"
            " WHERE status IN ('proposed', 'confirmed')"
            " GROUP BY lower(subject) HAVING COUNT(DISTINCT fact) > 1"
        ).fetchall()]


def set_canon_status(card_id: int, status: str) -> None:
    with connect() as db:
        db.execute("UPDATE canon_cards SET status = ? WHERE id = ?", (status, card_id))
        db.commit()


def delete_canon_card(card_id: int) -> None:
    with connect() as db:
        db.execute("DELETE FROM canon_cards WHERE id = ?", (card_id,))
        db.commit()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "nav" not in st.session_state:
    st.session_state.nav = "\u2302 Grand Hall"
if "selected_wing" not in st.session_state:
    st.session_state.selected_wing = None
if "revealed" not in st.session_state:
    st.session_state.revealed = set()
if "pending_delete" not in st.session_state:
    st.session_state.pending_delete = None
if "quiz" not in st.session_state:
    st.session_state.quiz = {
        "active": False, "order": [], "idx": 0, "revealed": False,
        "scored": False, "remembered": 0, "answered": 0, "finished": False,
        "wings_visited": [],
    }


def start_quiz(scope_wing):
    pool = list_memories(wing=scope_wing) if scope_wing else list_memories()
    order = [m["id"] for m in pool]
    random.shuffle(order)
    st.session_state.quiz = {
        "active": True, "order": order, "idx": 0, "revealed": False,
        "scored": False, "remembered": 0, "answered": 0, "finished": False,
        "wings_visited": [],
    }


def badge(text: str, kind: str = "gold") -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'


def wing_label(wing: str) -> str:
    info = WINGS.get(wing)
    if info:
        return f'{info["icon"]} {wing}'
    return wing

# ---------------------------------------------------------------------------
# Page setup + Sherlock cinematic CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Julian's Mind Palace",
    page_icon="\U0001f3db\ufe0f",
    layout="wide",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Inter:wght@400;500;600&display=swap');
.stApp {
  background: radial-gradient(circle at 70% 0, #1e2424 0, #0c0f10 45%);
  color: #e7e1d5;
}
section[data-testid="stSidebar"] { background-color: #0e1112; border-right: 1px solid #303536; }
section[data-testid="stSidebar"] * { color: #e7e1d5; }
h1, h2, h3, h4 { font-family: "Cormorant Garamond", serif !important; color: #e7e1d5 !important; }
p, li, span, div, label { font-family: Inter, system-ui, sans-serif; }
.subtitle { color: #8f928c; font-size: 1.05rem; margin-top: -0.6rem; }
.kicker { letter-spacing: 3px; color: #b99659; font-size: 0.7rem; text-transform: uppercase; }
.metric-card {
  background: linear-gradient(145deg, #1b2020, #131718);
  border: 1px solid #303536; border-radius: 16px; padding: 18px 20px; text-align: center;
}
.metric-card .value { font-family: "Cormorant Garamond", serif; font-size: 2.1rem; font-weight: 600; color: #e7e1d5; line-height: 1.1; }
.metric-card .label { font-size: 0.75rem; letter-spacing: 0.12em; text-transform: uppercase; color: #8f928c; margin-top: 4px; }
.wing-card {
  background: linear-gradient(145deg, #1b2020, #131718);
  border: 1px solid #303536; border-radius: 16px; padding: 20px; min-height: 170px;
}
.wing-card.selected { border: 2px solid #b99659; box-shadow: 0 0 0 3px rgba(185,150,89,0.15); }
.wing-card .wing-icon { font-size: 1.8rem; color: #b99659; }
.wing-card .wing-name { font-family: "Cormorant Garamond", serif; font-size: 1.45rem; font-weight: 600; color: #e7e1d5; margin-top: 6px; }
.wing-card .wing-desc { font-size: 0.88rem; color: #8f928c; margin-top: 4px; line-height: 1.5; }
.memory-card {
  background: linear-gradient(145deg, #1b2020, #131718);
  border: 1px solid #303536; border-radius: 16px; padding: 20px; margin-bottom: 14px;
  border-top: 1px solid #b99659;
}
.memory-card .location { font-size: 0.65rem; color: #b99659; text-transform: uppercase; letter-spacing: 1.5px; }
.memory-card .mem-title { font-family: "Cormorant Garamond", serif; font-size: 1.4rem; font-weight: 600; color: #e7e1d5; margin: 8px 0 6px; }
.memory-card .mem-body { font-size: 0.9rem; line-height: 1.6; color: #a8aaa5; white-space: pre-wrap; }
.memory-card .mem-tags { font-size: 0.75rem; color: #747975; margin-top: 10px; }
.memory-card .mem-meta { font-size: 0.72rem; color: #747975; margin-top: 4px; }
.blurred { filter: blur(6px); user-select: none; pointer-events: none; }
.faded { opacity: 0.55; }
.fogged { opacity: 0.65; font-style: italic; }
.badge {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
}
.badge-gold { background: rgba(185,150,89,0.18); color: #b99659; border: 1px solid rgba(185,150,89,0.45); }
.badge-blue { background: rgba(88,166,255,0.15); color: #58a6ff; border: 1px solid rgba(88,166,255,0.4); }
.badge-green { background: rgba(126,231,135,0.15); color: #7ee787; border: 1px solid rgba(126,231,135,0.4); }
.badge-red { background: rgba(255,123,114,0.15); color: #ff7b72; border: 1px solid rgba(255,123,114,0.4); }
.badge-grey { background: rgba(139,148,158,0.15); color: #8b949e; border: 1px solid rgba(139,148,158,0.4); }
.badge-orange { background: rgba(255,166,87,0.15); color: #ffa657; border: 1px solid rgba(255,166,87,0.4); }
.quote {
  border-left: 1px solid #b99659; padding-left: 25px; margin: 0;
  font-family: "Cormorant Garamond", serif; font-style: italic; font-size: 1.15rem; color: #b9b6ae;
}
.quote cite { display: block; font-family: Inter, sans-serif; font-style: normal; font-size: 0.65rem; margin-top: 9px; letter-spacing: 1px; text-transform: uppercase; color: #8f928c; }
.quiz-cue {
  background: linear-gradient(145deg, #1b2020, #131718);
  border: 1px solid #303536; border-radius: 16px; padding: 28px; text-align: center;
}
.quiz-cue .cue-label { font-size: 0.75rem; letter-spacing: 0.14em; text-transform: uppercase; color: #8f928c; }
.quiz-cue .cue-text { font-family: "Cormorant Garamond", serif; font-size: 1.8rem; font-weight: 600; color: #e7e1d5; margin-top: 8px; }
.reveal-box {
  background: rgba(126,231,135,0.08); border: 1px solid rgba(126,231,135,0.45);
  border-radius: 16px; padding: 22px; text-align: center; margin-top: 16px;
}
.reveal-box .reveal-text { font-family: "Cormorant Garamond", serif; font-size: 1.35rem; font-weight: 600; color: #7ee787; }
.thread { border-left: 2px solid #b99659; background: #171b1c; padding: 14px 16px; margin-bottom: 10px; border-radius: 0 12px 12px 0; }
div.stButton > button { border-radius: 10px; font-weight: 600; }
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
  background-color: #161b26 !important; color: #e7e1d5 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
NAV_OPTIONS = [
    "\u2302 Grand Hall",
    "\U0001f3db\ufe0f Palace Wings",
    "\u2795 Add Memory",
    "\u2301 Recall Mode",
    "\U0001f50d Instruments",
    "\U0001f4cb Browse & Manage",
]
st.sidebar.markdown(
    '<div style="font-family:\'Cormorant Garamond\',serif; font-size:1.5rem; color:#b99659;">'
    "JB</div>"
    '<div style="font-size:0.65rem; letter-spacing:3px; color:#b99659;">JULIAN\u2019S</div>'
    '<div style="font-family:\'Cormorant Garamond\',serif; font-size:1.4rem; font-weight:600;">'
    "Mind Palace</div>",
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")
nav_choice = st.sidebar.radio(
    "Navigate the palace",
    options=NAV_OPTIONS,
    index=NAV_OPTIONS.index(st.session_state.nav) if st.session_state.nav in NAV_OPTIONS else 0,
    label_visibility="collapsed",
)
st.session_state.nav = nav_choice
total = total_memories()
st.sidebar.markdown("---")
st.sidebar.markdown(
    f'<span style="color:#8f928c; font-size:0.8rem;">\u25cf Local vault active<br>'
    f"{total} {'memory' if total == 1 else 'memories'} secured<br>"
    "Nothing leaves this machine.</span>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def memory_card(mem: dict, key_prefix: str, allow_delete: bool = True):
    """Render one memory as a Sherlock-style card with its actions."""
    wing = mem["wing"]
    info = WINGS.get(wing, {})
    accent = info.get("accent", "#b99659")
    private = wing in PRIVATE_WINGS
    revealed = mem["id"] in st.session_state.revealed
    faded = is_faded(mem)
    created = (mem.get("created_at") or "")[:10]
    recalled = mem.get("last_recalled")
    age_note = ""
    if faded:
        anchor = recalled or mem.get("created_at")
        age = days_since(anchor)
        age_note = f" &middot; Fading &mdash; unrecalled for {age} days"
    body_class = "mem-body blurred" if (private and not revealed) else "mem-body"
    title_class = "mem-title blurred" if (private and not revealed) else "mem-title"
    card_class = "memory-card faded" if faded else "memory-card"
    tags = ", ".join(parse_tags(mem["tags"])) or "Untagged observation"
    safe_title = html.escape(mem["title"])
    safe_body = html.escape(mem["content"])
    safe_tags = html.escape(tags)
    safe_room = html.escape(mem["room"])
    safe_wing = html.escape(wing)
    st.markdown(
        f'<div class="{card_class}">'
        f'<div class="location" style="color:{accent}">{safe_wing} / {safe_room}</div>'
        f'<div class="{title_class}">{safe_title}</div>'
        f'<div class="{body_class}">{safe_body}</div>'
        f'<div class="mem-tags">\u2301 {safe_tags}</div>'
        f'<div class="mem-meta">Filed {created}'
        + (f' &middot; Recalled {mem.get("recall_count", 0)} times' if mem.get("recall_count") else "")
        + age_note
        + "</div></div>",
        unsafe_allow_html=True,
    )
    badges = []
    if private:
        badges.append(badge("Private", "red"))
    if faded:
        badges.append(badge("Fading", "grey"))
    if badges:
        st.markdown(" ".join(badges), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    if private:
        with c1:
            label = "Hide again" if revealed else "Reveal"
            if st.button(label, key=f"{key_prefix}_reveal_{mem['id']}"):
                if revealed:
                    st.session_state.revealed.discard(mem["id"])
                else:
                    st.session_state.revealed.add(mem["id"])
                st.rerun()
    if st.session_state.pending_delete == mem["id"]:
        with c2:
            if st.button("Confirm delete", key=f"{key_prefix}_delok_{mem['id']}"):
                delete_memory(mem["id"])
                st.session_state.pending_delete = None
                st.success(f"Deleted \u201c{mem['title'][:50]}\u201d. Nothing else was touched.")
                st.rerun()
        with c3:
            if st.button("Cancel", key=f"{key_prefix}_delno_{mem['id']}"):
                st.session_state.pending_delete = None
                st.rerun()
    else:
        with c2:
            if st.button("Seal as canon", key=f"{key_prefix}_canon_{mem['id']}"):
                add_canon_card(mem["id"], wing, mem["room"], mem["title"], mem["content"])
                st.success(f"\u201c{mem['title'][:50]}\u201d sealed as proposed canon. Confirm it in the Canon Vault.")
                st.rerun()
        if allow_delete:
            with c3:
                if st.button("Delete", key=f"{key_prefix}_del_{mem['id']}"):
                    st.session_state.pending_delete = mem["id"]
                    st.rerun()


def room_selector(wing: str, key: str):
    """Room picker: the wing's suggested rooms, plus a free-text custom room."""
    rooms = WINGS[wing]["rooms"]
    choice = st.selectbox("Room", options=rooms + ["Other \u2026"], key=f"{key}_room_pick")
    if choice == "Other \u2026":
        custom = st.text_input("Custom room name", key=f"{key}_room_custom", placeholder="e.g. The Red Study")
        return custom.strip()
    return choice


# ---------------------------------------------------------------------------
# View: Grand Hall
# ---------------------------------------------------------------------------
if nav_choice == "\u2302 Grand Hall":
    st.markdown('<div class="kicker">Private Archive / London</div>', unsafe_allow_html=True)
    st.markdown("# What are we deducing?")
    st.markdown(
        '<p class="subtitle">Search the whole palace, or walk in through the wings. '
        "Every memory is stored locally and never leaves this machine.</p>",
        unsafe_allow_html=True,
    )

    counts = wing_counts()
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(
            f'<div class="metric-card"><div class="value">{total}</div>'
            '<div class="label">Case files secured</div></div>',
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f'<div class="metric-card"><div class="value">{len(counts)}</div>'
            '<div class="label">Wings in use</div></div>',
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            f'<div class="metric-card"><div class="value">{total_tags()}</div>'
            '<div class="label">Distinct tags</div></div>',
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            f'<div class="metric-card"><div class="value">{total_recall_rounds()}</div>'
            '<div class="label">Recall rounds</div></div>',
            unsafe_allow_html=True,
        )
    with k5:
        faded_count = len(faded_memories())
        st.markdown(
            f'<div class="metric-card"><div class="value" style="color:#8f928c">{faded_count}</div>'
            '<div class="label">Fading memories</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        '<blockquote class="quote">\u201cThe world is full of obvious things which nobody '
        "by any chance ever observes.\u201d"
        "<cite>Arthur Conan Doyle</cite></blockquote>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    query = st.text_input(
        "Search the palace",
        placeholder="Search a person, clue, decision, place, or idea\u2026",
        key="hall_search",
    )
    if query.strip():
        results = list_memories(query=query.strip())
        st.markdown(f"### {len(results)} result{'s' if len(results) != 1 else ''} for \u201c{query.strip()}\u201d")
        if not results:
            st.info("The corridor is quiet. No matching memory was found — an empty room is an invitation.")
        for mem in results:
            memory_card(mem, "hall")
    else:
        st.markdown("### Recently observed")
        recent = list_memories()[:6]
        if not recent:
            st.info(
                "The palace is empty — an invitation, not a failure. "
                "Place your first memory from the \u201cAdd Memory\u201d view, or jot a quick "
                "note in the Pocket Notebook under Instruments."
            )
        for mem in recent:
            memory_card(mem, "hall")

# ---------------------------------------------------------------------------
# View: Palace Wings
# ---------------------------------------------------------------------------
elif nav_choice == "\U0001f3db\ufe0f Palace Wings":
    st.markdown('<div class="kicker">The Method of Loci</div>', unsafe_allow_html=True)
    st.markdown("# The Nine Wings")
    st.markdown(
        '<p class="subtitle">Every memory lives in a wing and a room. '
        "Choose a wing to browse what it holds.</p>",
        unsafe_allow_html=True,
    )
    counts = wing_counts()
    wing_names = STORAGE_WINGS
    for row in range(3):
        cols = st.columns(3)
        for j, wing in enumerate(wing_names[row * 3: row * 3 + 3]):
            info = WINGS[wing]
            count = counts.get(wing, 0)
            selected = st.session_state.selected_wing == wing
            css = "wing-card selected" if selected else "wing-card"
            with cols[j]:
                st.markdown(
                    f'<div class="{css}">'
                    f'<div class="wing-icon">{info["icon"]}</div>'
                    f'<div class="wing-name">{wing}</div>'
                    f'<div class="wing-desc">{info["description"]}</div>'
                    f'<div style="margin-top:12px;">'
                    f'{badge(str(count) + " " + ("memory" if count == 1 else "memories"), "gold" if count else "grey")} '
                    + (badge("Private", "red") if info["private"] else "")
                    + (badge("Selected", "blue") if selected else "")
                    + "</div></div>",
                    unsafe_allow_html=True,
                )
                label = f"Viewing {wing}" if selected else f"Enter {wing}"
                if st.button(label, key=f"enter_{wing}", use_container_width=True):
                    st.session_state.selected_wing = None if selected else wing
                    st.session_state.nav = "\U0001f4cb Browse & Manage"
                    st.rerun()
    # Ninth wing: Recall Mode
    st.markdown("---")
    rounds = total_recall_rounds()
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            f'<div class="wing-card">'
            f'<div class="wing-icon">\u2301</div>'
            f'<div class="wing-name">Recall Mode</div>'
            f'<div class="wing-desc">Reconstruct a path from a question to its exact source. '
            f"Quiz yourself on what the palace holds — only the room and a cue are shown "
            f"until you reveal the memory.</div>"
            f'<div style="margin-top:12px;">{badge(str(rounds) + " recall rounds", "gold" if rounds else "grey")}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Enter Recall Mode", key="enter_recall", use_container_width=True):
            st.session_state.nav = "\u2301 Recall Mode"
            st.rerun()

# ---------------------------------------------------------------------------
# View: Add Memory
# ---------------------------------------------------------------------------
elif nav_choice == "\u2795 Add Memory":
    st.markdown('<div class="kicker">New Observation</div>', unsafe_allow_html=True)
    st.markdown("# Place it in the palace")
    st.markdown(
        '<p class="subtitle">Record the observation verbatim. Give it a wing, a room, '
        "and tags — the palace does the remembering from there.</p>",
        unsafe_allow_html=True,
    )
    # Wing lives outside the form so changing it refreshes the room list.
    wing = st.selectbox("Wing", options=STORAGE_WINGS, key="add_wing")
    with st.form("memory_form", clear_on_submit=True):
        room = room_selector(wing, "add")
        title = st.text_input("Memory title", placeholder="e.g. The overlooked detail")
        content = st.text_area(
            "What must not be forgotten?",
            placeholder="Record the observation verbatim\u2026",
            height=160,
        )
        tags = st.text_input("Tags (comma-separated)", placeholder="e.g. clue, london, urgent")
        submitted = st.form_submit_button("Secure memory", use_container_width=True)
        if submitted:
            if not room:
                st.error("A room is required — every memory needs a place to live.")
            elif not title.strip():
                st.error("A title is required — name the memory so you can find it again.")
            elif not content.strip():
                st.error("The memory itself is required — write down what must not be forgotten.")
            else:
                new_id = add_memory(wing, room, title, content, tags)
                st.success(
                    f"Memory secured in {wing} / {room}. "
                    f"It is now memory #{new_id} in your palace."
                )

# ---------------------------------------------------------------------------
# View: Recall Mode
# ---------------------------------------------------------------------------
elif nav_choice == "\u2301 Recall Mode":
    st.markdown('<div class="kicker">Reconstruction Engine</div>', unsafe_allow_html=True)
    st.markdown("# Enter the corridors of memory")
    st.markdown(
        '<p class="subtitle">You see only the room and a cue. Recall the memory in '
        "your mind, reveal it, and score yourself honestly. Every round is logged — "
        "and every recall refreshes the memory so it stops fading.</p>",
        unsafe_allow_html=True,
    )
    quiz = st.session_state.quiz
    scope = st.selectbox(
        "Recall scope",
        options=["All wings"] + STORAGE_WINGS,
        key="quiz_scope",
    )
    scope_wing = None if scope == "All wings" else scope
    pool = list_memories(wing=scope_wing) if scope_wing else list_memories()
    st.markdown(
        f'{badge("Scope: " + scope, "blue")} '
        f'{badge(str(len(pool)) + " " + ("memory" if len(pool) == 1 else "memories") + " available", "grey")}',
        unsafe_allow_html=True,
    )

    if not quiz["active"]:
        if st.button("Begin recall", key="quiz_start", use_container_width=True):
            if not pool:
                st.warning("There is nothing to recall yet — add some memories first.")
            else:
                start_quiz(scope_wing)
                st.rerun()
        if pool:
            st.info(
                "Recall Mode shows the room and the memory's title as your cue. "
                "The full memory stays hidden until you choose to reveal it."
            )
    else:
        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown(
                f'<div class="metric-card"><div class="value" style="color:#7ee787">'
                f'{quiz["remembered"]}</div><div class="label">Remembered</div></div>',
                unsafe_allow_html=True,
            )
        with s2:
            st.markdown(
                f'<div class="metric-card"><div class="value">{quiz["answered"]}</div>'
                '<div class="label">Answered</div></div>',
                unsafe_allow_html=True,
            )
        with s3:
            remaining = max(len(quiz["order"]) - quiz["idx"], 0)
            st.markdown(
                f'<div class="metric-card"><div class="value" style="color:#58a6ff">'
                f'{remaining}</div><div class="label">Remaining</div></div>',
                unsafe_allow_html=True,
            )

        if not quiz["order"]:
            st.info("There are no memories to recall in this scope. Add some first, or widen the scope.")
            if st.button("End recall", key="quiz_empty_end"):
                st.session_state.quiz["active"] = False
                st.rerun()
        elif quiz["finished"] or quiz["idx"] >= len(quiz["order"]):
            st.session_state.quiz["finished"] = True
            total_q = quiz["answered"]
            remembered = quiz["remembered"]
            pct = round(100 * remembered / total_q) if total_q else 0
            if pct >= 80:
                verdict = badge("Strong recall", "green")
            elif pct >= 50:
                verdict = badge("Getting there", "gold")
            else:
                verdict = badge("Needs more practice", "red")
            path = "  \u2192  ".join(dict.fromkeys(quiz["wings_visited"])) or "Grand Hall"
            st.markdown("### Recall complete")
            st.markdown(
                f'<div class="quiz-cue"><div class="cue-label">Final score</div>'
                f'<div class="cue-text">{remembered} / {total_q} remembered ({pct}%)</div>'
                f'<div style="margin-top:12px;">{verdict}</div>'
                f'<div style="margin-top:14px; color:#8f928c; font-size:0.9rem;">'
                f"Path walked: {html.escape(path)}</div></div>",
                unsafe_allow_html=True,
            )
            if st.button("Recall again", key="quiz_restart_done", use_container_width=True):
                start_quiz(scope_wing)
                st.rerun()
            if st.button("End recall", key="quiz_end_done"):
                st.session_state.quiz["active"] = False
                st.rerun()
        else:
            current = get_memory(quiz["order"][quiz["idx"]])
            if current is None:
                st.error("That memory no longer exists — rebuilding the recall round.")
                start_quiz(scope_wing)
                st.rerun()
            else:
                st.markdown(
                    f"**Question {quiz['idx'] + 1} of {len(quiz['order'])}**"
                )
                st.markdown(
                    f'<div class="quiz-cue">'
                    f'<div class="cue-label">Room</div>'
                    f'<div style="margin-top:6px;">{badge(wing_label(current["wing"]) + " / " + html.escape(current["room"]), "gold")}</div>'
                    f'<div class="cue-label" style="margin-top:18px;">The cue</div>'
                    f'<div class="cue-text">{html.escape(current["title"])}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if not quiz["revealed"]:
                    if st.button("Reveal memory", key="quiz_reveal", use_container_width=True):
                        st.session_state.quiz["revealed"] = True
                        st.rerun()
                else:
                    st.markdown(
                        f'<div class="reveal-box">'
                        f'<div class="cue-label" style="color:#7ee787;">The memory</div>'
                        f'<div class="reveal-text">{html.escape(current["content"])}</div>'
                        f'<div style="margin-top:10px; color:#8f928c; font-size:0.85rem;">'
                        f'Tags: {html.escape(", ".join(parse_tags(current["tags"])) or "none")}</div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if not quiz["scored"]:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("I remembered it", key="quiz_yes", use_container_width=True):
                                log_recall(current["id"], True)
                                st.session_state.quiz["remembered"] += 1
                                st.session_state.quiz["answered"] += 1
                                st.session_state.quiz["scored"] = True
                                if current["wing"] not in st.session_state.quiz["wings_visited"]:
                                    st.session_state.quiz["wings_visited"].append(current["wing"])
                                st.rerun()
                        with c2:
                            if st.button("I missed it", key="quiz_no", use_container_width=True):
                                log_recall(current["id"], False)
                                st.session_state.quiz["answered"] += 1
                                st.session_state.quiz["scored"] = True
                                if current["wing"] not in st.session_state.quiz["wings_visited"]:
                                    st.session_state.quiz["wings_visited"].append(current["wing"])
                                st.rerun()
                    else:
                        st.success("Score recorded. Ready for the next one?")
                        if st.button("Next memory", key="quiz_next", use_container_width=True):
                            st.session_state.quiz["idx"] += 1
                            st.session_state.quiz["revealed"] = False
                            st.session_state.quiz["scored"] = False
                            if st.session_state.quiz["idx"] >= len(st.session_state.quiz["order"]):
                                st.session_state.quiz["finished"] = True
                            st.rerun()
        st.markdown("---")
        if st.button("Restart recall", key="quiz_restart_mid"):
            start_quiz(scope_wing)
            st.rerun()
        if st.button("End recall", key="quiz_end_mid"):
            st.session_state.quiz["active"] = False
            st.rerun()

# ---------------------------------------------------------------------------
# View: Instruments
# ---------------------------------------------------------------------------
elif nav_choice == "\U0001f50d Instruments":
    st.markdown('<div class="kicker">Palace Instruments</div>', unsafe_allow_html=True)
    st.markdown("# Instruments of deduction")
    st.markdown(
        '<p class="subtitle">Seven instruments, one palace. Each works on the '
        "memories you have actually stored — nothing invented.</p>",
        unsafe_allow_html=True,
    )
    inst_tabs = st.tabs([
        "Deduction Board",
        "Timeline Corridor",
        "Daily Ritual",
        "Memory Decay",
        "Privacy Doors",
        "Pocket Notebook",
        "Canon Vault",
    ])

    # --- Deduction Board ---
    with inst_tabs[0]:
        st.markdown("### Deduction Board")
        st.markdown(
            "Threads reveal which people, topics, and case files repeatedly intersect. "
            "A tag shared by two or more memories is a thread worth pulling."
        )
        all_mems = list_memories()
        tag_map = {}
        for mem in all_mems:
            for tag in parse_tags(mem["tags"]):
                tag_map.setdefault(tag, []).append(mem)
        if not tag_map:
            st.info("The board awaits evidence. Add tags to your memories and the threads will appear here.")
        else:
            st.markdown("**Tag cloud**")
            cloud = "  ".join(
                badge(f"{html.escape(tag)} ({len(mems)})", "blue" if len(mems) > 1 else "grey")
                for tag, mems in sorted(tag_map.items(), key=lambda kv: -len(kv[1]))
            )
            st.markdown(cloud, unsafe_allow_html=True)
            st.markdown("---")
            threads = {t: ms for t, ms in tag_map.items() if len(ms) >= 2}
            if not threads:
                st.info("No tag is shared by more than one memory yet — no threads to follow.")
            else:
                st.markdown(f"### {len(threads)} thread{'s' if len(threads) != 1 else ''} on the board")
                shown = 0
                for tag, mems in sorted(threads.items(), key=lambda kv: -len(kv[1])):
                    if shown >= 20:
                        break
                    shown += 1
                    st.markdown(
                        f'<div class="thread"><b>&#9670; {html.escape(tag)}</b> &mdash; '
                        f"{len(mems)} linked memories</div>",
                        unsafe_allow_html=True,
                    )
                    for mem in mems[:5]:
                        st.markdown(
                            f"- **{html.escape(mem['title'])}** &mdash; "
                            f"{html.escape(mem['wing'])} / {html.escape(mem['room'])}"
                        )
                    if len(mems) > 5:
                        st.markdown(f"- *and {len(mems) - 5} more*")

    # --- Timeline Corridor ---
    with inst_tabs[1]:
        st.markdown("### Timeline Corridor")
        st.markdown("Walk through your history in chronological order, oldest first.")
        all_mems = sorted(list_memories(), key=lambda m: (m.get("created_at") or "", m.get("id", 0)))
        if not all_mems:
            st.info("The corridor is empty. File your first memory and its place in time will appear here.")
        else:
            groups = {}
            for mem in all_mems:
                month = (mem.get("created_at") or "Undated")[:7]
                groups.setdefault(month, []).append(mem)
            for month in sorted(groups):
                st.markdown(f"#### {month}")
                for mem in groups[month]:
                    faded_mark = " *(fading)*" if is_faded(mem) else ""
                    st.markdown(
                        f"- **{(mem.get('created_at') or '')[:10]}** — **{html.escape(mem['title'])}**"
                        f" &mdash; {html.escape(mem['wing'])} / {html.escape(mem['room'])}{faded_mark}"
                    )

    # --- Daily Observation Ritual ---
    with inst_tabs[2]:
        st.markdown("### Daily Observation Ritual")
        st.markdown("A minute of deliberate observation prevents important details from fading.")
        day_index = datetime.now(timezone.utc).timetuple().tm_yday % len(RITUAL_PROMPTS)
        prompt = RITUAL_PROMPTS[day_index]
        st.markdown(
            f'<blockquote class="quote">{html.escape(prompt)}</blockquote>',
            unsafe_allow_html=True,
        )
        if ritual_done_today():
            st.success("Today's ritual is complete — the observation is filed in People & Life / Daily Observations.")
        else:
            st.markdown(f'{badge("Ritual pending", "gold")}', unsafe_allow_html=True)
        with st.form("ritual_form", clear_on_submit=True):
            r_title = st.text_input("Name this observation", placeholder="e.g. The barista remembered my order")
            r_content = st.text_area("Observe before explaining\u2026", height=120)
            r_submit = st.form_submit_button("Place in the palace", use_container_width=True)
            if r_submit:
                if not r_title.strip():
                    st.error("Give the observation a name.")
                elif not r_content.strip():
                    st.error("Write down what you observed.")
                else:
                    add_memory("People & Life", "Daily Observations", r_title, r_content, "daily-ritual")
                    st.success("Today's observation is filed. The palace remembers it so you don't have to.")
                    st.rerun()

    # --- Memory Decay ---
    with inst_tabs[3]:
        st.markdown("### Memory Decay")
        st.markdown(
            f"Memories unrecalled for more than {DECAY_DAYS} days visibly fade — "
            "a quiet reminder to revisit them. **Nothing is ever deleted.** "
            "Recalling a memory (in Recall Mode or with Revisit below) restores it."
        )
        faded = faded_memories()
        st.markdown(
            f'{badge(str(len(faded)) + " fading", "grey")} '
            f'{badge(str(total - len(faded)) + " fresh", "green")}',
            unsafe_allow_html=True,
        )
        if not faded:
            st.info("Nothing is fading. Every memory has been recalled recently — or the palace is still new.")
        for mem in faded:
            anchor = mem.get("last_recalled") or mem.get("created_at")
            age = days_since(anchor)
            st.markdown(
                f'<div class="memory-card faded">'
                f'<div class="location">{html.escape(mem["wing"])} / {html.escape(mem["room"])}</div>'
                f'<div class="mem-title">{html.escape(mem["title"])}</div>'
                f'<div class="mem-meta">Unrecalled for {age} days &middot; filed {(mem.get("created_at") or "")[:10]}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button("Revisit — mark recalled now", key=f"revisit_{mem['id']}"):
                touch_memory(mem["id"])
                st.success(f"\u201c{mem['title'][:50]}\u201d is fresh again.")
                st.rerun()

    # --- Privacy Doors ---
    with inst_tabs[4]:
        st.markdown("### Privacy Doors")
        st.markdown(
            "Health Observatory and Legal & Finance Vault previews stay blurred until "
            "you deliberately reveal them. This is a visual privacy curtain for "
            "over-the-shoulder glances — not database encryption. The data itself "
            "never leaves this machine."
        )
        private_mems = [m for m in list_memories() if m["wing"] in PRIVATE_WINGS]
        st.markdown(
            f'{badge(str(len(private_mems)) + " sealed memories", "red")} '
            f'{badge(str(len(st.session_state.revealed)) + " currently revealed", "grey")}',
            unsafe_allow_html=True,
        )
        if not private_mems:
            st.info("No sealed memories yet. Anything filed under Health Observatory or Legal & Finance Vault will be curtained here.")
        for mem in private_mems:
            memory_card(mem, "privacy")

    # --- Pocket Notebook ---
    with inst_tabs[5]:
        st.markdown("### Pocket Notebook")
        st.markdown("Unsorted thoughts, captured in seconds — place them in the palace when you have a moment.")
        unplaced = list_pocket_notes(0)
        placed = list_pocket_notes(1)
        st.markdown(
            f'{badge(str(len(unplaced)) + " awaiting placement", "gold" if unplaced else "grey")} '
            f'{badge(str(len(placed)) + " placed", "green" if placed else "grey")}',
            unsafe_allow_html=True,
        )
        with st.form("pocket_form", clear_on_submit=True):
            note_text = st.text_area("Jot it down", placeholder="A half-formed thought, a name, a number\u2026", height=90)
            note_submit = st.form_submit_button("Pocket it", use_container_width=True)
            if note_submit:
                if not note_text.strip():
                    st.error("Write the thought down first — even a fragment counts.")
                else:
                    add_pocket_note(note_text)
                    st.success("Pocketed. It will wait here until you place it.")
                    st.rerun()
        if unplaced:
            st.markdown("### Awaiting placement")
            for note in unplaced:
                st.markdown(
                    f'<div class="thread"><b>Note #{note["id"]}</b> &middot; {(note.get("created_at") or "")[:16]}'
                    f'<br>{html.escape(note["text"])}</div>',
                    unsafe_allow_html=True,
                )
                with st.expander(f"Place note #{note['id']} in the palace"):
                    # Wing lives outside the form so changing it refreshes the room list.
                    p_wing = st.selectbox("Wing", options=STORAGE_WINGS, key=f"pw_{note['id']}")
                    with st.form(f"place_{note['id']}"):
                        p_room = room_selector(p_wing, f"pn_{note['id']}")
                        p_title = st.text_input("Memory title", key=f"pt_{note['id']}", placeholder="Name this memory")
                        p_go = st.form_submit_button("Place it")
                        if p_go:
                            if not p_room:
                                st.error("A room is required.")
                            elif not p_title.strip():
                                st.error("Give the memory a title.")
                            else:
                                place_pocket_note(note["id"], p_wing, p_room, p_title)
                                st.success(f"Placed in {p_wing} / {p_room}.")
                                st.rerun()
        if placed:
            with st.expander(f"Placed notes ({len(placed)})"):
                for note in placed:
                    st.markdown(f"- {html.escape(note['text'][:120])}")

    # --- Canon Vault ---
    with inst_tabs[6]:
        st.markdown("### Canon Vault & Contradiction Alarm")
        st.markdown(
            "Only you can confirm canon. Proposed cards stay fogged until confirmed, "
            "and multiple versions of the same subject raise an alarm. "
            "Seal a memory as canon from any memory card."
        )
        contradictions = canon_contradictions()
        if contradictions:
            for contra in contradictions:
                st.warning(
                    f"Contradiction: \u201c{contra['subject']}\u201d has {contra['versions']} "
                    "incompatible versions. Your judgment is required."
                )
        cards = list_canon_cards()
        confirmed = sum(1 for c in cards if c["status"] == "confirmed")
        st.markdown(
            f'{badge(str(confirmed) + " confirmed", "green")} '
            f'{badge(str(len(cards) - confirmed) + " proposed", "gold")}',
            unsafe_allow_html=True,
        )
        if not cards:
            st.info("No canon seals have been placed yet. Use \u201cSeal as canon\u201d on any memory card.")
        for card in cards:
            proposed = card["status"] == "proposed"
            card_class = "memory-card fogged" if proposed else "memory-card"
            st.markdown(
                f'<div class="{card_class}">'
                f'<div class="location">{html.escape(card["wing"])} / {html.escape(card["room"])}</div>'
                f'<div class="mem-title">{html.escape(card["subject"])}</div>'
                f'<div class="mem-body">{html.escape(card["fact"])}</div>'
                f'<div class="mem-meta">Sealed {(card.get("created_at") or "")[:10]}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(badge(card["status"], "gold" if proposed else "green"), unsafe_allow_html=True)
            cc1, cc2 = st.columns(2)
            if proposed:
                with cc1:
                    if st.button("Confirm canon", key=f"canon_ok_{card['id']}"):
                        set_canon_status(card["id"], "confirmed")
                        st.success(f"\u201c{card['subject'][:50]}\u201d is now confirmed canon.")
                        st.rerun()
            with cc2:
                if st.button("Discard", key=f"canon_del_{card['id']}"):
                    delete_canon_card(card["id"])
                    st.success("Canon card discarded. The source memory is untouched.")
                    st.rerun()

# ---------------------------------------------------------------------------
# View: Browse & Manage
# ---------------------------------------------------------------------------
elif nav_choice == "\U0001f4cb Browse & Manage":
    st.markdown('<div class="kicker">The Case Files</div>', unsafe_allow_html=True)
    st.markdown("# Browse & Manage")
    f1, f2 = st.columns(2)
    with f1:
        wing_filter = st.selectbox(
            "Wing",
            options=["All wings"] + STORAGE_WINGS,
            index=(STORAGE_WINGS.index(st.session_state.selected_wing) + 1)
            if st.session_state.selected_wing in STORAGE_WINGS else 0,
            key="browse_wing",
        )
    with f2:
        room_filter = st.text_input(
            "Room contains (optional)", placeholder="e.g. Study", key="browse_room"
        )
    if wing_filter != "All wings":
        st.session_state.selected_wing = wing_filter
    elif st.session_state.selected_wing:
        st.session_state.selected_wing = None
    view = list_memories(
        wing=None if wing_filter == "All wings" else wing_filter,
        room=room_filter.strip() or None,
    )
    st.markdown(
        f'{badge("Showing " + str(len(view)) + " of " + str(total) + " memories", "blue")}',
        unsafe_allow_html=True,
    )
    if st.session_state.selected_wing:
        if st.button("Clear wing filter", key="browse_clear"):
            st.session_state.selected_wing = None
            st.rerun()
    if not view:
        st.info("No memories match. Loosen the filters, or add a memory from the Add Memory view.")
    for mem in view:
        memory_card(mem, "browse")

st.markdown("---")
st.markdown(
    '<p style="color:#8f928c; font-size:0.85rem;">Julian\u2019s Mind Palace — '
    "memories live locally in <code>palace.db</code> next to this app. "
    "Private wings stay blurred until revealed. Fading is visual only; "
    "nothing is ever deleted. Your palace, your data.</p>",
    unsafe_allow_html=True,
)
