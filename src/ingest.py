"""Indexing pipeline: load markdown docs -> chunk -> embed -> store in Chroma.

Run from project root:  python -m src.ingest
"""
import glob
import os

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from src import config

load_dotenv()


def load_and_chunk():
    """Load every markdown file and split it into header-based chunks."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=config.HEADERS_TO_SPLIT_ON,
        strip_headers=False,          # keep headers inside the text — they carry meaning
    )
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.MAX_CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )

    all_chunks = []
    for path in sorted(glob.glob(f"{config.KNOWLEDGE_BASE_DIR}/*.md")):
        source = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            text = f.read()

        # Pass 1: split on headers (semantic boundaries)
        chunks = header_splitter.split_text(text)

        # Pass 2: safety net — re-split any chunk that's still too large
        chunks = size_splitter.split_documents(chunks)

        # Attach source metadata for citations later
        for c in chunks:
            c.metadata["source"] = source

        print(f"{source}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    return all_chunks


def main():
    chunks = load_and_chunk()
    print(f"\nTotal: {len(chunks)} chunks. Embedding and storing...")

    embeddings = OpenAIEmbeddings(model=config.EMBEDDING_MODEL)
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=config.COLLECTION_NAME,
        persist_directory=config.CHROMA_PERSIST_DIR,
    )
    print(f"Done. Vector store persisted to ./{config.CHROMA_PERSIST_DIR}/")


if __name__ == "__main__":
    main()
