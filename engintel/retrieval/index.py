"""Vector + BM25 index over the chunks table, persisted to data/index/.
Upsert semantics: vectors are keyed by chunk_id, so re-indexing overwrites."""
import pickle

from .. import config, store
from .bm25 import BM25
from .embed import get_embedder

INDEX_FILE = "index.pkl"

def build_index(embedder_kind=None):
    kind = embedder_kind or config.EMBEDDER
    chunks = store.query("SELECT chunk_id, doc_id, source, section, page, element_type, text FROM chunks ORDER BY source, chunk_index")
    if not chunks:
        raise RuntimeError("no chunks to index; run ingestion first")
    texts = [c["text"] for c in chunks]
    emb = get_embedder(kind).fit(texts)
    vectors = emb.encode(texts)
    idx = {"chunks": chunks, "vectors": vectors, "embedder": emb, "embedder_name": emb.name}
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.INDEX_DIR / INDEX_FILE, "wb") as f:
        pickle.dump(idx, f)
    with store.tx() as con:
        con.execute("UPDATE chunks SET embedding_model=?", (emb.name,))
    return {"chunks": len(chunks), "embedder": emb.name}

_cache = {}
def load_index():
    path = config.INDEX_DIR / INDEX_FILE
    mtime = path.stat().st_mtime
    if _cache.get("mtime") != mtime:
        with open(path, "rb") as f:
            idx = pickle.load(f)
        idx["bm25"] = BM25([c["text"] for c in idx["chunks"]])
        _cache.update(idx=idx, mtime=mtime)
    return _cache["idx"]

def dense_scores(idx, query):
    q = idx["embedder"].encode([query])[0]
    return (idx["vectors"] @ q).tolist()
