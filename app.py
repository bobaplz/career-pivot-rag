"""Streamlit UI — thin wrapper around the RAG chain."""
import streamlit as st

from src.rag_chain import build_chain

st.set_page_config(page_title="Career Pivot Knowledge Base", page_icon="📚")

st.title("📚 Career Pivot Knowledge Base")
st.caption(
    "Ask questions about SQL, pandas, A/B testing, ML model selection, or RAG. "
    "Answers are grounded in my hand-written knowledge base — with citations."
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

if question := st.chat_input("e.g. Why does NOT IN return no rows with NULLs?"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving and answering..."):
            answer = chain(question)
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})
