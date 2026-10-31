"""Hybrid retrieval: dense + BM25 -> reciprocal rank fusion -> optional cross-encoder rerank."""
from .. import config
from .index import dense_scores, load_index
from .text import tokenize

def _rank(scores, filt, limit):
    order = sorted((i for i in range(len(scores)) if filt(i)), key=lambda i: scores[i], reverse=True)
    return order[:limit]

def rrf(rankings, k=60):
    """RRF: score(d) = sum over rankings of 1/(k + rank). Uses ranks, not raw scores, so BM25
    and cosine (different scales) can be combined without normalisation."""
    fused = {}
    for ranking in rankings:
        for r, i in enumerate(ranking, start=1):
            fused[i] = fused.get(i, 0.0) + 1.0 / (k + r)
    return sorted(fused, key=fused.get, reverse=True)

_reranker = None
def _rerank(query, cands, chunks):
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    scores = _reranker.predict([(query, chunks[i]["text"]) for i in cands])
    return [i for _, i in sorted(zip(scores, cands), reverse=True)]

def retrieve(query, k=5, mode="hybrid", filters=None, rerank=None):
    idx = load_index()
    chunks = idx["chunks"]
    filters = filters or {}
    filt = lambda i: all(chunks[i].get(f) == v for f, v in filters.items())
    if mode == "dense":
        order = _rank(dense_scores(idx, query), filt, 30)
    elif mode == "bm25":
        order = _rank(idx["bm25"].scores(query), filt, 30)
    else:
        order = rrf([_rank(dense_scores(idx, query), filt, 30),
                     _rank(idx["bm25"].scores(query), filt, 30)])[:30]
    if rerank if rerank is not None else config.RERANK:
        order = _rerank(query, order, chunks)
    q_terms = set(tokenize(query))
    out = []
    for i in order[:k]:
        c = dict(chunks[i])
        c_terms = set(tokenize(c["text"]))
        c["term_coverage"] = round(len(q_terms & c_terms) / max(len(q_terms), 1), 3)
        out.append(c)
    return out
