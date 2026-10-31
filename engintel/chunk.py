"""Section-aware chunking. Prose: split within a section by word window with overlap.
Tables: kept whole as one chunk with a generated caption (splitting a table destroys it)."""
import hashlib
from . import config

def chunk_id(doc_id, idx):
    # deterministic: same doc + same position -> same ID, so retries overwrite, never duplicate
    return hashlib.sha256(f"{doc_id}:{idx}".encode()).hexdigest()[:16]

def chunk_elements(doc_id, source, elements, target=None, overlap=None, title=None):
    target = target or config.CHUNK_TARGET_WORDS
    overlap = overlap or config.CHUNK_OVERLAP_WORDS
    # merge consecutive prose elements of the same section first
    merged = []
    for e in elements:
        if e["element_type"] == "needs_ocr":
            continue
        if (merged and e["element_type"] == "text" and merged[-1]["element_type"] == "text"
                and merged[-1]["section"] == e["section"]):
            merged[-1]["text"] += " " + e["text"]
        else:
            merged.append(dict(e))
    chunks = []
    for e in merged:
        if e["element_type"] == "table":
            pieces = [header(title, e) + e["text"]]
        else:
            words = e["text"].split()
            step = max(target - overlap, 1)
            pieces = [" ".join(words[i:i + target]) for i in range(0, max(len(words) - overlap, 1), step)]
            pieces = [header(title, e) + p for p in pieces if p.strip()]
        for p in pieces:
            idx = len(chunks)
            chunks.append(dict(chunk_id=chunk_id(doc_id, idx), doc_id=doc_id, source=source,
                               section=e["section"], page=e["page"], element_type=e["element_type"],
                               text=p, chunk_index=idx))
    return chunks

def header(title, e):
    """Contextual chunk header: doc title + section travel with every chunk, so a chunk that
    says 'the secondary unit takes over' is still findable by 'brake'."""
    return f"[{title} > {e['section']}] " if title else f"[{e['section']}] "

def doc_title(elements):
    for e in elements:
        if e["section"] == "Front matter" and e["element_type"] == "text" and e["text"]:
            return " ".join(e["text"].split()[:14])
    return None
