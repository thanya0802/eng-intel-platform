# Build log

Notes on what broke, why, and what changed.

## Initial build
- A corrupt PDF is retried five times, then lands in the dead-letter queue with the parser's error.
  A parse error is permanent, so it could skip retries; Pub/Sub semantics were kept for now.
- A scan-like PDF (no text layer) was re-parsed on every upload, because deduplication treated only
  `processed` as terminal. `needs_ocr` is terminal too; caught by `test_reupload_after_success_is_noop`.
- "Which change requests are closed…" included CR-13 (open) from a document passage about a
  different failure. When the records return a chain, document passages whose IDs don't overlap
  the chain are now dropped.
- "What is CR-13 changing…" missed "silver plating" because the relevant chunk shared few words with
  the question. Chunks mentioning an ID from the question are now admitted as evidence.
- "What caused the HV-7 failures?" still fails in extractive mode: the answer sentence shares no
  words with the question. That is the case for an LLM synthesizer.
- Retrieval is saturated on the synthetic corpus (recall@5 = 1.0 in every mode).

## Running on a second machine
- Lint rules weren't enforced locally; imports are now one per line and the line limit is 140
  (document text in data/corpus.py is exempt).
- Tests are hermetic: a GEMINI_API_KEY in the shell no longer switches them to the real API.
- LLM calls retry rate limits with backoff and tolerate text after the JSON reply.

## Extractive vs. Gemini answers
- With Gemini writing answers, the agent eval scored 13/15, below extractive mode (14/15), and still
  missed the HV-7 case. The passage with the answer ("fretting corrosion") was retrieved but dropped
  by the coverage filter before the model saw it: the bottleneck was evidence selection, not
  answer writing. In LLM mode all top retrieved passages now go to the model, which is told to
  ignore irrelevant ones and trust structured records over passages when they conflict.
- Gemini described CR-13's failure without naming FAIL-88. The answer prompt now asks for record
  IDs exactly as they appear in the evidence.
