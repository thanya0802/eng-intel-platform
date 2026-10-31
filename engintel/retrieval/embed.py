"""Embedders behind one interface, so the vector store doesn't care which model runs.

lsa   : TF-IDF + truncated SVD (Latent Semantic Analysis). Offline, deterministic, no
        download. It is a *weak* dense baseline: say so honestly in your README.
sbert : sentence-transformers all-MiniLM-L6-v2. Real neural embeddings, runs on CPU.
On GCP the same interface wraps a Vertex AI text-embedding model.
"""
import numpy as np

class LSAEmbedder:
    name = "lsa-tfidf-svd"
    def __init__(self, dim=128):
        self.dim = dim
    def fit(self, texts):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=1)
        X = self.vec.fit_transform(texts)
        self.svd = TruncatedSVD(n_components=min(self.dim, X.shape[1] - 1, X.shape[0] - 1), random_state=0)
        self.svd.fit(X)
        return self
    def encode(self, texts):
        Z = self.svd.transform(self.vec.transform(texts))
        return Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)

class SBERTEmbedder:
    name = "all-MiniLM-L6-v2"
    def fit(self, texts):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return self
    def encode(self, texts):
        return np.asarray(self.model.encode(list(texts), normalize_embeddings=True))

def get_embedder(kind):
    return {"lsa": LSAEmbedder, "sbert": SBERTEmbedder}[kind]()
