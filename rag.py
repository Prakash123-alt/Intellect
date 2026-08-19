"""ChromaDB-backed RAG helpers for the Exam Prediction Assistant.

Uploaded exam documents (previous year papers / question banks) are chunked
and embedded into a persistent Chroma collection so relevant passages can be
retrieved as context for AI-based topic/question prediction.
"""
import os
import logging

logger = logging.getLogger('rag')

CHROMA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'chroma')
os.makedirs(CHROMA_DIR, exist_ok=True)

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        import chromadb
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_or_create_collection('exam_documents')
    return _collection


def chunk_text(text, chunk_size=1000, overlap=150):
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    return chunks


def index_document(doc_id, subject, doc_type, text, year=None):
    """Chunk a document's text and add it to the Chroma collection."""
    chunks = chunk_text(text)
    if not chunks:
        return 0
    try:
        coll = _get_collection()
        ids = [f"doc{doc_id}_chunk{i}" for i in range(len(chunks))]
        metadatas = [{
            'doc_id': doc_id,
            'subject': subject,
            'doc_type': doc_type,
            'year': year or ''
        } for _ in chunks]
        coll.add(documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)
    except Exception as e:
        logger.error(f"Failed to index document {doc_id} into Chroma: {e}")
        return 0


def query_context(subject, query_text, doc_type=None, top_k=10):
    """Retrieve the most relevant chunks for a subject (optionally filtered by doc_type)."""
    try:
        coll = _get_collection()
        where = {'subject': subject} if doc_type is None else {
            '$and': [{'subject': subject}, {'doc_type': doc_type}]
        }
        result = coll.query(query_texts=[query_text], n_results=top_k, where=where)
        docs = result.get('documents', [[]])[0]
        return docs
    except Exception as e:
        logger.error(f"Chroma query failed: {e}")
        return []


def delete_subject_documents(subject):
    """Remove all indexed chunks for a subject (used when re-analyzing from scratch)."""
    try:
        coll = _get_collection()
        coll.delete(where={'subject': subject})
    except Exception as e:
        logger.error(f"Failed to delete Chroma docs for subject {subject}: {e}")
