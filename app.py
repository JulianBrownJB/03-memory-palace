"""Memory Recall Memory Palace — a visual memory palace for storing facts
and drilling active recall.

Streamlit app. Stores memory anchors in palace_data.json next to this file.
Rooms: Grand Foyer, Library, Study, The Vault.
"""
import json
import random
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_FILE = Path(__file__).parent / "palace_data.json"
CORRUPT_BACKUP = Path(__file__).parent / "palace_data.json.corrupt"

ROOMS = {
    "Grand Foyer": {
        "icon": "🏛️",
        "description": "The grand entrance — first impressions, foundations, and the ideas you meet first.",
        "accent": "#e8b64c",
    },
    "Library": {
        "icon": "📚",
        "description": "Endless shelves — knowledge, quotes, references, and everything worth keeping.",
        "accent": "#58a6ff",
    },
    "Study": {
        "icon": "🖋️",
        "description": "The quiet desk — focus, formulas, deep work, and things that take concentration.",
        "accent": "#7ee787",
    },
    "The Vault": {
        "icon": "🔐",
        "description": "Locked away — your most precious, high-value memories, guarded and secure.",
        "accent": "#d2a8ff",
    },
}

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def load_anchors():
    """Load anchors from palace_data.json.

    Missing file -> empty list. Corrupt file -> back it up to
    palace_data.json.corrupt, flag a warning, and start empty.
    """
    if not DATA_FILE.exists():
        return [], False
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("palace_data.json must contain a JSON list")
        return data, False
    except (json.JSONDecodeError, ValueError):
        shutil.copy2(DATA_FILE, CORRUPT_BACKUP)
        return [], True


def save_anchors(anchors):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(anchors, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "anchors" not in st.session_state:
    loaded, corrupt = load_anchors()
    st.session_state.anchors = loaded
    st.session_state.corrupt_warning = corrupt
if "selected_room" not in st.session_state:
    st.session_state.selected_room = None
if "quiz_active" not in st.session_state:
    st.session_state.quiz_active = False
if "quiz_order" not in st.session_state:
    st.session_state.quiz_order = []
if "quiz_idx" not in st.session_state:
    st.session_state.quiz_idx = 0
if "quiz_revealed" not in st.session_state:
    st.session_state.quiz_revealed = False
if "quiz_scored" not in st.session_state:
    st.session_state.quiz_scored = False
if "quiz_remembered" not in st.session_state:
    st.session_state.quiz_remembered = 0
if "quiz_answered" not in st.session_state:
    st.session_state.quiz_answered = 0
if "quiz_finished" not in st.session_state:
    st.session_state.quiz_finished = False


def room_count(room):
    return sum(1 for a in st.session_state.anchors if a.get("room") == room)


def start_quiz():
    """Build a fresh shuffled quiz order, honouring the room filter."""
    pool = st.session_state.anchors
    if st.session_state.selected_room:
        pool = [a for a in pool if a.get("room") == st.session_state.selected_room]
    order = [a["id"] for a in pool]
    random.shuffle(order)
    st.session_state.quiz_order = order
    st.session_state.quiz_idx = 0
    st.session_state.quiz_revealed = False
    st.session_state.quiz_scored = False
    st.session_state.quiz_remembered = 0
    st.session_state.quiz_answered = 0
    st.session_state.quiz_finished = False
    st.session_state.quiz_active = True


def get_anchor(anchor_id):
    for a in st.session_state.anchors:
        if a["id"] == anchor_id:
            return a
    return None


# ---------------------------------------------------------------------------
# Page setup + custom CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Memory Recall Memory Palace",
    page_icon="🏛️",
    layout="wide",
)

st.markdown(
    """
<style>
  .stApp { background-color: #0b0e14; color: #e6edf3; }
  h1, h2, h3 { color: #f0f6fc !important; }
  .subtitle { color: #8b949e; font-size: 1.05rem; margin-top: -0.6rem; }
  .metric-card {
    background: linear-gradient(145deg, #161b26, #10141d);
    border: 1px solid #2d333b;
    border-radius: 16px;
    padding: 18px 20px;
    text-align: center;
  }
  .metric-card .value { font-size: 2rem; font-weight: 800; color: #f0f6fc; line-height: 1.1; }
  .metric-card .label { font-size: 0.8rem; letter-spacing: 0.12em; text-transform: uppercase; color: #8b949e; margin-top: 4px; }
  .room-card {
    background: linear-gradient(145deg, #161b26, #10141d);
    border: 1px solid #2d333b;
    border-radius: 16px;
    padding: 20px;
    min-height: 150px;
  }
  .room-card.selected { border: 2px solid #e8b64c; box-shadow: 0 0 0 3px rgba(232,182,76,0.15); }
  .room-card .room-icon { font-size: 2rem; }
  .room-card .room-name { font-size: 1.25rem; font-weight: 700; color: #f0f6fc; margin-top: 6px; }
  .room-card .room-desc { font-size: 0.9rem; color: #8b949e; margin-top: 4px; line-height: 1.45; }
  .badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  }
  .badge-gold { background: rgba(232,182,76,0.18); color: #e8b64c; border: 1px solid rgba(232,182,76,0.45); }
  .badge-blue { background: rgba(88,166,255,0.15); color: #58a6ff; border: 1px solid rgba(88,166,255,0.4); }
  .badge-green { background: rgba(126,231,135,0.15); color: #7ee787; border: 1px solid rgba(126,231,135,0.4); }
  .badge-red { background: rgba(255,123,114,0.15); color: #ff7b72; border: 1px solid rgba(255,123,114,0.4); }
  .badge-grey { background: rgba(139,148,158,0.15); color: #8b949e; border: 1px solid rgba(139,148,158,0.4); }
  .quiz-cue {
    background: linear-gradient(145deg, #161b26, #10141d);
    border: 1px solid #2d333b; border-radius: 16px; padding: 28px; text-align: center;
  }
  .quiz-cue .cue-label { font-size: 0.8rem; letter-spacing: 0.14em; text-transform: uppercase; color: #8b949e; }
  .quiz-cue .cue-text { font-size: 1.7rem; font-weight: 700; color: #f0f6fc; margin-top: 8px; }
  .concept-reveal {
    background: rgba(126,231,135,0.08); border: 1px solid rgba(126,231,135,0.45);
    border-radius: 16px; padding: 22px; text-align: center; margin-top: 16px;
  }
  .concept-reveal .concept-text { font-size: 1.4rem; font-weight: 700; color: #7ee787; }
  .hint-box {
    background: rgba(88,166,255,0.08); border: 1px solid rgba(88,166,255,0.35);
    border-radius: 12px; padding: 14px 18px; margin-top: 14px; color: #c9d8ff;
  }
  .section-head { margin-top: 8px; margin-bottom: 4px; }
  div.stButton > button { border-radius: 10px; font-weight: 600; }
  .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
    background-color: #161b26 !important; color: #e6edf3 !important;
  }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# 🏛️ Memory Recall Memory Palace")
st.markdown(
    '<p class="subtitle">Store what matters in themed rooms — then drill it back '
    "with active recall.</p>",
    unsafe_allow_html=True,
)

if st.session_state.get("corrupt_warning"):
    st.warning(
        "⚠️ Your previous palace_data.json was corrupt, so it was backed up to "
        "palace_data.json.corrupt and a fresh empty palace was started. "
        "Your old file is safe in the backup."
    )

# ---------------------------------------------------------------------------
# KPI metric cards
# ---------------------------------------------------------------------------
total = len(st.session_state.anchors)
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(
        f'<div class="metric-card"><div class="value">{total}</div>'
        '<div class="label">Total Anchors</div></div>',
        unsafe_allow_html=True,
    )
for col, room in zip((m2, m3, m4, m5), ROOMS):
    accent = ROOMS[room]["accent"]
    st.markdown(
        f'<div class="metric-card"><div class="value" style="color:{accent}">'
        f'{room_count(room)}</div><div class="label">{room}</div></div>',
        unsafe_allow_html=True,
    )

# Room filter indicator
if st.session_state.selected_room:
    fcol1, fcol2 = st.columns([5, 1])
    with fcol1:
        st.markdown(
            f'<span class="badge badge-gold">Filtered: '
            f'{st.session_state.selected_room}</span> '
            f'<span style="color:#8b949e"> — the grid, quiz, and browse views '
            f"focus on this room.</span>",
            unsafe_allow_html=True,
        )
    with fcol2:
        if st.button("✕ Clear filter", key="clear_filter"):
            st.session_state.selected_room = None
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_palace, tab_add, tab_quiz, tab_browse = st.tabs(
    ["🏛️ Palace", "➕ Add Anchor", "🧠 Quiz Mode", "📋 Browse & Manage"]
)

# ============================ PALACE TAB ==================================
with tab_palace:
    st.markdown("### Choose a room")
    st.markdown(
        '<p class="subtitle">Select a room to focus the palace on it — '
        "the quiz and browse views follow your selection.</p>",
        unsafe_allow_html=True,
    )
    room_names = list(ROOMS.keys())
    for row in range(2):
        cols = st.columns(2)
        for j, room in enumerate(room_names[row * 2 : row * 2 + 2]):
            info = ROOMS[room]
            count = room_count(room)
            selected = st.session_state.selected_room == room
            css_class = "room-card selected" if selected else "room-card"
            badge = (
                '<span class="badge badge-gold">● Selected</span>'
                if selected
                else ""
            )
            with cols[j]:
                st.markdown(
                    f'<div class="{css_class}">'
                    f'<div class="room-icon">{info["icon"]}</div>'
                    f'<div class="room-name">{room}</div>'
                    f'<div class="room-desc">{info["description"]}</div>'
                    f'<div style="margin-top:12px;">'
                    f'<span class="badge badge-blue">{count} '
                    f'{"anchor" if count == 1 else "anchors"}</span> {badge}'
                    f"</div></div>",
                    unsafe_allow_html=True,
                )
                label = (
                    f"✓ Viewing {room}" if selected else f"Enter {room}"
                )
                if st.button(label, key=f"enter_{room}", use_container_width=True):
                    st.session_state.selected_room = (
                        None if selected else room
                    )
                    st.rerun()

# ============================ ADD ANCHOR TAB ==============================
with tab_add:
    st.markdown("### ➕ New Memory Anchor")
    st.markdown(
        '<p class="subtitle">Place a fact in a room, give it a vivid sensory '
        "association, and a trigger cue you will use to recall it.</p>",
        unsafe_allow_html=True,
    )
    with st.form("anchor_form", clear_on_submit=True):
        room = st.selectbox("Room", options=list(ROOMS.keys()))
        concept = st.text_input(
            "Concept / Fact",
            placeholder="e.g. The capital of Australia is Canberra",
        )
        sensory = st.text_area(
            "Vivid Sensory Association",
            placeholder="e.g. Picture a kangaroo in a beret sipping coffee on a parliament balcony — smell the eucalyptus, hear the accent.",
            height=110,
        )
        cue = st.text_input(
            "Recall Trigger Cue",
            placeholder="e.g. Kangaroo + parliament",
        )
        submitted = st.form_submit_button("💾 Save Anchor", use_container_width=True)
        if submitted:
            if not concept.strip():
                st.error("❌ A concept / fact is required — the anchor needs something to remember.")
            elif not cue.strip():
                st.error("❌ A recall trigger cue is required — it is how you will pull the memory back.")
            else:
                anchor = {
                    "id": uuid.uuid4().hex[:12],
                    "room": room,
                    "concept": concept.strip(),
                    "sensory": sensory.strip(),
                    "cue": cue.strip(),
                    "created": datetime.now().isoformat(timespec="seconds"),
                }
                st.session_state.anchors.append(anchor)
                save_anchors(st.session_state.anchors)
                st.success(
                    f"✅ Anchor saved to the {room} — "
                    f'"{anchor["concept"][:60]}" is now in your palace.'
                )

# ============================ QUIZ TAB ====================================
with tab_quiz:
    st.markdown("### 🧠 Active Recall — Quiz Mode")
    st.markdown(
        '<p class="subtitle">You see only the room and the trigger cue. '
        "Recall the concept in your mind, reveal it, and score yourself honestly.</p>",
        unsafe_allow_html=True,
    )

    pool_size = len(
        [
            a
            for a in st.session_state.anchors
            if not st.session_state.selected_room
            or a.get("room") == st.session_state.selected_room
        ]
    )
    scope = st.session_state.selected_room or "All rooms"
    st.markdown(
        f'<span class="badge badge-blue">Scope: {scope}</span> '
        f'<span class="badge badge-grey">{pool_size} '
        f'{"item" if pool_size == 1 else "items"} available</span>',
        unsafe_allow_html=True,
    )

    quiz_on = st.toggle(
        "Enter Quiz Mode",
        value=st.session_state.quiz_active,
        key="quiz_toggle",
    )
    if quiz_on and not st.session_state.quiz_active:
        start_quiz()
        st.rerun()
    if not quiz_on and st.session_state.quiz_active:
        st.session_state.quiz_active = False
        st.rerun()

    if st.session_state.quiz_active:
        # Score row
        s1, s2, s3 = st.columns(3)
        with s1:
            st.markdown(
                f'<div class="metric-card"><div class="value" style="color:#7ee787">'
                f'{st.session_state.quiz_remembered}</div>'
                '<div class="label">Remembered</div></div>',
                unsafe_allow_html=True,
            )
        with s2:
            st.markdown(
                f'<div class="metric-card"><div class="value">'
                f'{st.session_state.quiz_answered}</div>'
                '<div class="label">Answered</div></div>',
                unsafe_allow_html=True,
            )
        with s3:
            remaining = max(len(st.session_state.quiz_order) - st.session_state.quiz_idx, 0)
            st.markdown(
                f'<div class="metric-card"><div class="value" style="color:#58a6ff">'
                f'{remaining}</div><div class="label">Remaining</div></div>',
                unsafe_allow_html=True,
            )

        if not st.session_state.quiz_order:
            st.info(
                "📭 There are no memory anchors to quiz yet"
                + (
                    f" in the **{st.session_state.selected_room}**."
                    if st.session_state.selected_room
                    else "."
                )
                + " Add some anchors first, or clear the room filter."
            )
            if st.button("➕ Go add an anchor", key="quiz_empty_add"):
                st.session_state.quiz_active = False
                st.rerun()
        elif st.session_state.quiz_finished or st.session_state.quiz_idx >= len(
            st.session_state.quiz_order
        ):
            st.session_state.quiz_finished = True
            total_q = st.session_state.quiz_answered
            remembered = st.session_state.quiz_remembered
            pct = round(100 * remembered / total_q) if total_q else 0
            badge = (
                '<span class="badge badge-green">Strong recall</span>'
                if pct >= 80
                else '<span class="badge badge-gold">Getting there</span>'
                if pct >= 50
                else '<span class="badge badge-red">Needs more practice</span>'
            )
            st.markdown("### 🎉 Quiz complete!")
            st.markdown(
                f'<div class="quiz-cue"><div class="cue-label">Final score</div>'
                f'<div class="cue-text">{remembered} / {total_q} remembered '
                f"({pct}%)</div>"
                f'<div style="margin-top:12px;">{badge}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("🔁 Restart quiz", key="quiz_restart_done", use_container_width=True):
                start_quiz()
                st.rerun()
        else:
            current = get_anchor(st.session_state.quiz_order[st.session_state.quiz_idx])
            if current is None:
                st.error("That anchor no longer exists — restarting the quiz.")
                start_quiz()
                st.rerun()
            else:
                st.markdown(
                    f"**Question {st.session_state.quiz_idx + 1} of "
                    f"{len(st.session_state.quiz_order)}**"
                )
                accent = ROOMS[current["room"]]["accent"]
                st.markdown(
                    f'<div class="quiz-cue">'
                    f'<div class="cue-label">Room</div>'
                    f'<div style="margin-top:6px;"><span class="badge badge-gold">'
                    f'{ROOMS[current["room"]]["icon"]} {current["room"]}</span></div>'
                    f'<div class="cue-label" style="margin-top:18px;">Trigger cue</div>'
                    f'<div class="cue-text">{current["cue"]}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

                show_hint = st.checkbox(
                    "💡 Show sensory hint", key="quiz_hint"
                )
                if show_hint:
                    hint = current.get("sensory") or "(No sensory note was saved for this anchor.)"
                    st.markdown(
                        f'<div class="hint-box">👃 <b>Sensory association:</b> {hint}</div>',
                        unsafe_allow_html=True,
                    )

                if not st.session_state.quiz_revealed:
                    if st.button(
                        "👁️ Reveal Memory", key="quiz_reveal", use_container_width=True
                    ):
                        st.session_state.quiz_revealed = True
                        st.rerun()
                else:
                    st.markdown(
                        f'<div class="concept-reveal">'
                        f'<div class="cue-label" style="color:#7ee787;">The memory</div>'
                        f'<div class="concept-text">{current["concept"]}</div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if not st.session_state.quiz_scored:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(
                                "✅ I remembered it",
                                key="quiz_yes",
                                use_container_width=True,
                            ):
                                st.session_state.quiz_remembered += 1
                                st.session_state.quiz_answered += 1
                                st.session_state.quiz_scored = True
                                st.rerun()
                        with c2:
                            if st.button(
                                "❌ I missed it",
                                key="quiz_no",
                                use_container_width=True,
                            ):
                                st.session_state.quiz_answered += 1
                                st.session_state.quiz_scored = True
                                st.rerun()
                    else:
                        st.success("Score recorded. Ready for the next one?")
                        if st.button(
                            "➡️ Next", key="quiz_next", use_container_width=True
                        ):
                            st.session_state.quiz_idx += 1
                            st.session_state.quiz_revealed = False
                            st.session_state.quiz_scored = False
                            if st.session_state.quiz_idx >= len(st.session_state.quiz_order):
                                st.session_state.quiz_finished = True
                            st.rerun()

        st.markdown("---")
        if st.button("🔁 Restart quiz", key="quiz_restart_mid"):
            start_quiz()
            st.rerun()

# ============================ BROWSE TAB ==================================
with tab_browse:
    st.markdown("### 📋 All Memory Anchors")
    view = st.session_state.anchors
    if st.session_state.selected_room:
        view = [a for a in view if a.get("room") == st.session_state.selected_room]
    st.markdown(
        f'<span class="badge badge-blue">Showing {len(view)} of {total} anchors</span>',
        unsafe_allow_html=True,
    )
    if not view:
        st.info(
            "📭 No anchors here yet. Add your first anchor from the "
            "“Add Anchor” tab to start building your palace."
        )
    else:
        # Header row
        h1, h2, h3, h4, h5 = st.columns([1.1, 1.6, 2.6, 2.4, 0.6])
        h1.markdown("**Room**")
        h2.markdown("**Trigger Cue**")
        h3.markdown("**Concept / Fact**")
        h4.markdown("**Sensory Association**")
        h5.markdown("**Del**")
        st.markdown("---")
        for anchor in sorted(view, key=lambda a: (a.get("room", ""), a.get("cue", ""))):
            c1, c2, c3, c4, c5 = st.columns([1.1, 1.6, 2.6, 2.4, 0.6])
            accent = ROOMS.get(anchor.get("room"), {}).get("accent", "#8b949e")
            c1.markdown(
                f'<span style="color:{accent}; font-weight:700;">'
                f'{ROOMS.get(anchor.get("room"), {}).get("icon", "")} '
                f'{anchor.get("room", "")}</span>',
                unsafe_allow_html=True,
            )
            c2.write(anchor.get("cue", ""))
            c3.write(anchor.get("concept", ""))
            c4.write(anchor.get("sensory", "") or "—")
            if c5.button("🗑️", key=f"del_{anchor['id']}", help="Delete this anchor"):
                st.session_state.anchors = [
                    a for a in st.session_state.anchors if a["id"] != anchor["id"]
                ]
                save_anchors(st.session_state.anchors)
                st.success(f"🗑️ Deleted “{anchor.get('cue', '')}”.")
                st.rerun()

st.markdown("---")
st.markdown(
    '<p style="color:#8b949e; font-size:0.85rem;">Memory Recall Memory Palace — '
    "anchors are stored locally in <code>palace_data.json</code>. "
    "Your palace, your data.</p>",
    unsafe_allow_html=True,
)
