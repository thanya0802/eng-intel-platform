"""BM25 (Okapi), written out so you can explain every term in an interview.
score(q,d) = sum_t idf(t) * tf(t,d)*(k1+1) / (tf(t,d) + k1*(1 - b + b*|d|/avgdl))"""
import math
from collections import Counter
from .text import tokenize

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = sum(self.lens) / max(len(self.lens), 1)
        df = Counter(t for tf in self.tfs for t in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query):
        q = tokenize(query)
        out = []
        for tf, dl in zip(self.tfs, self.lens):
            s = 0.0
            for t in q:
                if t in tf:
                    s += self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out
