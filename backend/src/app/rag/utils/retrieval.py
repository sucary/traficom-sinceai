import os

import faiss
import numpy as np

from app.rag.utils.processing import get_embedder


def retrieve_relevant_chunks(query, embedder=None, k=5, index_path="faiss_index.idx", chunks_path="text_chunks.npy"):
    if embedder is None:
        embedder = get_embedder()
    index = faiss.read_index(os.fspath(index_path))
    chunks = np.load(os.fspath(chunks_path), allow_pickle=True)
    query_embedding = embedder.encode([query], convert_to_numpy=True)
    _, indices = index.search(query_embedding, k)

    retrieved_chunks = [chunks[i] for i in indices[0] if i >= 0]
    return retrieved_chunks
