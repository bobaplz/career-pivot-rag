# RAG (Retrieval-Augmented Generation): Concepts

## The problem RAG solves

An LLM answering from its weights alone is taking a **closed-book exam**: its knowledge is frozen at training time, it knows nothing about your private documents, and when it doesn't know, it often produces fluent, confident, wrong answers (hallucination) rather than "I don't know." RAG turns this into an **open-book exam**: at question time, retrieve the relevant passages from your own corpus and hand them to the model, instructing it to answer *from those passages*.

Compared to fine-tuning, RAG is: **updatable** (add a document to the index vs retrain), **cheaper** (no GPU training), **auditable** (you can show exactly which passages produced the answer — citations), and **access-controllable** (retrieval can respect permissions). Fine-tuning teaches a model new *behavior* (style, format, domain reasoning); RAG gives it new *knowledge*. Most "the model doesn't know our data" problems are RAG problems, not fine-tuning problems.

## Embeddings: meaning as geometry

An embedding model maps text to a vector (typically 384–1536 dimensions) such that **similar meaning lands close together** in that space. "My policy was cancelled" and "the insurer terminated my coverage" share almost no words but sit near each other geometrically; distance (cosine similarity, usually) becomes a computable proxy for semantic relatedness.

This is what separates **semantic search** from keyword search: keyword search (BM25, SQL `LIKE`) matches strings, so it misses synonyms and paraphrases and can't rank "aboutness" — while semantic search matches meaning, finding the cancellation clause even when the question uses none of its words. The trade-off runs both ways: keyword search wins on exact identifiers (policy numbers, error codes, rare proper nouns) that embeddings blur. Production systems often run both and merge results (**hybrid search**).

## The two pipelines

RAG is two separate pipelines that share one thing: the embedding model.

### Indexing (one-time, offline)

**Load → chunk → embed → store.** Load documents (PDFs, HTML, transcripts), split them into chunks, run each chunk through the embedding model, and store the vectors (with the original text and metadata) in a vector database (Chroma, FAISS, pgvector, Pinecone). Rerun incrementally when documents change.

### Query (per question, online)

**Embed the question → similarity search → top-k chunks → LLM.** Embed the user's question *with the same model*, find the k nearest chunks in the vector DB, stuff them into a prompt alongside the question, and have the LLM generate an answer grounded in them.

**Why the same embedding model for questions and documents?** Because similarity is only meaningful *within* one vector space. Two different models produce different, incompatible geometries — even with matching dimensions, "close" in model A's space says nothing in model B's. Embed queries with a different model than the index and your nearest-neighbor search returns geometric noise. Corollary: **changing the embedding model means re-embedding the entire corpus.**

## Key design decisions

### Chunking

Why split at all: (1) embeddings compress a passage into one vector — embed a 50-page document whole and the vector is a meaningless average of everything; (2) retrieval granularity — you want to fetch the *relevant paragraph*, not the whole file; (3) context budget — retrieved text must fit in the prompt.

The size trade-off: **too small** (a sentence) and chunks lose the context needed to be understood or to answer anything; **too large** (many pages) and each vector blurs multiple topics, retrieval precision drops, and you burn context window on irrelevant text. Common starting point: ~300–800 tokens with 10–15% overlap so sentences straddling a boundary aren't orphaned. Better than fixed sizes: split on natural structure (headings, paragraphs — "semantic chunking"), and attach metadata (source, section, date) to every chunk for filtering and citation.

### Top-k

How many chunks to retrieve. **Too few** and the answer's evidence may not make it into the prompt; **too many** and you add noise, cost, and "lost in the middle" degradation (LLMs attend less reliably to mid-context content). Typical starting point: k = 3–8. The refinement that matters most in practice: **retrieve wide, then rerank** — pull k = 20–50 cheaply with vector search, then use a reranker (cross-encoder) to reorder by true relevance and keep the best 3–5. Also set a similarity floor: if nothing scores above it, say so rather than stuffing weak matches.

### The prompt

The generation step is a prompt template combining instructions + retrieved chunks + question:

```
Answer the question using ONLY the context below.
If the context doesn't contain the answer, say you don't know.
Cite the source of each claim as [source].

Context:
[chunk 1 — source: claims_manual.pdf, p.12]
[chunk 2 — ...]

Question: {question}
```

Three load-bearing elements: **grounding instruction** ("only from context"), an **explicit I-don't-know escape hatch** (without it the model falls back to its weights and hallucinates), and **citation format** (pass each chunk's metadata in, require it in the answer — this is what makes RAG auditable).

## Why RAG reduces hallucination (but doesn't eliminate it)

RAG helps because the model no longer has to *recall* — it can *read*: correct evidence sits in the prompt, the instruction constrains the answer to it, and citations make claims checkable. But every stage can still fail: **retrieval misses** (the relevant chunk wasn't found, or the answer isn't in the corpus — the model may improvise); **imperfect grounding** (the model ignores context or blends it with its parametric knowledge); **faithful-to-wrong-source** (the retrieved document itself is outdated or incorrect — RAG faithfully reproduces garbage); **synthesis errors** (correct chunks, wrong combination). So evaluate the two stages separately: retrieval quality (does the right chunk appear in top-k? — recall@k) and generation faithfulness (is every claim supported by the retrieved text?). "RAG = no hallucination" is a claim to avoid; "grounded and citable, with measurable failure modes" is the honest version.

## RAG vs fine-tuning vs long context

| | RAG | Fine-tuning | Long context (stuff everything in) |
|---|---|---|---|
| Best for | External/changing knowledge, citations | Behavior: style, format, domain reasoning | Small, stable corpus that fits in one prompt |
| Knowledge updates | Re-index a document (minutes) | Retrain (hours–days, $$) | Edit the prompt |
| Cost profile | Cheap per-query + index upkeep | High upfront, cheap inference | Token cost grows with corpus every query |
| Traceability | Citations built in | None — knowledge is in weights | Possible but unranked |
| Weaknesses | Retrieval quality is the ceiling | Poor at adding facts; forgets; stale | Cost, latency, lost-in-the-middle |

They compose rather than compete: long context is fine when the whole corpus is a few dozen pages; RAG when it's thousands of documents or changes often; fine-tuning when the problem is *how* the model responds, not *what* it knows. A common production combo: RAG for knowledge + a lightly fine-tuned (or well-prompted) model for tone and format.
