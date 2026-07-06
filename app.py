"""Streamlit UI — thin wrapper around the RAG chain."""
import streamlit as st

from src import config
from src.rag_chain import build_chain

st.set_page_config(page_title="brain.db", page_icon="🧠")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');

:root{
  --bg:#0B0B0F; --text:#ECECF1; --muted:#8E8EA0;
  --glass:rgba(255,255,255,.055); --edge:rgba(255,255,255,.09);
  --cyan:#37C6FF; --violet:#7A5CFF; --pink:#FF5CA8;
}

.stApp{
  background:
    radial-gradient(60% 42% at 50% 0%, rgba(122,92,255,.16) 0%, rgba(122,92,255,0) 70%),
    var(--bg);
}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"], #MainMenu, footer{visibility:hidden}

/* --- Siri orb: outer div breathes (scale), inner div spins (rotate) --- */
.orb-wrap{display:flex;justify-content:center;padding:1.1rem 0 .3rem}
.orb-breathe{animation:breathe 4s ease-in-out infinite}
.orb{
  width:84px;height:84px;border-radius:50%;
  background:conic-gradient(var(--cyan),var(--violet),var(--pink),var(--cyan));
  filter:blur(13px) saturate(1.35);
  animation:spin 7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes breathe{0%,100%{transform:scale(.92)}50%{transform:scale(1.06)}}
@media (prefers-reduced-motion:reduce){.orb,.orb-breathe{animation:none}}

/* --- brand --- */
.stApp h1.brand{
  font-family:'JetBrains Mono',monospace !important;font-weight:700;
  font-size:2.7rem;text-align:center;letter-spacing:-.03em;margin:0;padding:0;
  background:linear-gradient(90deg,var(--cyan),var(--violet),var(--pink));
  -webkit-background-clip:text !important;background-clip:text !important;
  color:transparent !important;
}
.tagline{
  font-family:'JetBrains Mono',monospace;font-size:.78rem;line-height:1.7;
  color:var(--muted);text-align:center;margin:.7rem 0 .9rem;
}
.tagline .kw{color:var(--violet)}

/* --- category dropdown: pinned inside the chat input bar, left of send.
       Right-anchored so it stays glued to the send button at any window width:
       on wide screens the input column is 736px centered, below ~900px it's
       full-width, so the anchor falls back to a fixed offset. --- */
[data-testid="stElementContainer"]:has([data-testid="stSelectbox"]){
  position:fixed;z-index:1000;
  bottom:60px;width:140px !important;
  right:max(calc(50% - 368px + 62px), 62px);
}
[data-testid="stSelectbox"] [data-baseweb="select"]>div{
  background:transparent;border:none;
  font-family:'JetBrains Mono',monospace;font-size:.72rem;color:var(--muted);
  min-height:34px;display:flex;align-items:center;justify-content:flex-end;
}
/* value text and chevron: shrink to content so they sit together, centered */
[data-testid="stSelectbox"] [data-baseweb="select"]>div>div{
  flex:0 1 auto;padding:0;display:flex;align-items:center;
}
[data-testid="stSelectbox"] [data-baseweb="select"] *{text-transform:uppercase}
[data-testid="stSelectbox"] svg{color:var(--muted)}
ul[data-testid="stSelectboxVirtualDropdown"] li{
  font-family:'JetBrains Mono',monospace;font-size:.75rem;text-transform:uppercase;
}

/* --- chat bubbles: assistant left (glass), user right (aurora tint) --- */
[data-testid="stChatMessage"]{
  background:var(--glass);
  border:1px solid var(--edge);
  border-radius:20px;
  padding:.9rem 1.15rem;
  width:fit-content;max-width:86%;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){
  margin-left:auto;
  background:linear-gradient(135deg,rgba(55,198,255,.10),rgba(122,92,255,.16));
  border-color:rgba(122,92,255,.35);
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"]{display:none}

/* --- source caption under answers --- */
[data-testid="stChatMessage"] [data-testid="stCaptionContainer"] p{
  font-family:'JetBrains Mono',monospace;font-size:.66rem;color:var(--muted);
  margin-top:.2rem;
}

/* --- chat input: glass pill with aurora focus ring --- */
[data-testid="stBottom"]>div{background:transparent}
[data-testid="stChatInput"]{
  background:var(--glass);
  border:1px solid var(--edge);
  border-radius:999px;
}
[data-testid="stChatInput"]:focus-within{
  border-color:rgba(122,92,255,.6);
  box-shadow:0 0 0 1px rgba(122,92,255,.35),0 0 28px rgba(122,92,255,.25);
}
[data-testid="stChatInput"] textarea{background:transparent;font-size:16px;padding-right:180px}

/* --- mobile --- */
@media (max-width:640px){
  [data-testid="stMainBlockContainer"]{padding:2.5rem .9rem 1rem}
  .orb-wrap{padding:.5rem 0 .2rem}
  .orb{width:60px;height:60px;filter:blur(10px) saturate(1.35)}
  .stApp h1.brand{font-size:1.9rem}
  .tagline{font-size:.6rem;line-height:1.6;margin:.5rem 0 .7rem}
  [data-testid="stChatMessage"]{max-width:94%;padding:.7rem .9rem;border-radius:16px}
  [data-testid="stElementContainer"]:has([data-testid="stSelectbox"]){
    right:54px;width:112px !important;bottom:54px;
  }
  [data-testid="stChatInput"] textarea{padding-right:122px}
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)

st.markdown(
    """
    <div class="orb-wrap"><div class="orb-breathe"><div class="orb"></div></div></div>
    <h1 class="brand">brain.db</h1>
    <p class="tagline">
      <span class="kw">SELECT</span> answer <span class="kw">FROM</span> my_notes<br>
      <span class="kw">WHERE</span> topic <span class="kw">IN</span> ('sql', 'pandas', 'ab_testing', 'ml', 'rag');
    </p>
    """,
    unsafe_allow_html=True,
)

# Category picker — like a model selector, but for notes.
# Rendered here, then CSS-pinned into the chat input bar next to the send button.
ALL_NOTES = "✨ all"
category = st.selectbox(
    "category",
    options=[ALL_NOTES, *config.CATEGORIES],
    label_visibility="collapsed",
)

# Build once, reuse across reruns (Streamlit reruns the script on every interaction)
@st.cache_resource
def get_chain():
    return build_chain()

chain = get_chain()

# Chat history lives in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.caption("📎 " + " · ".join(msg["sources"]))

if question := st.chat_input("Ask my notes anything"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("querying brain.db..."):
            result = chain(question, category=None if category == ALL_NOTES else category)
        st.markdown(result["answer"])
        if result["sources"]:
            st.caption("📎 " + " · ".join(result["sources"]))

    st.session_state.messages.append(
        {"role": "assistant", "content": result["answer"], "sources": result["sources"]}
    )
