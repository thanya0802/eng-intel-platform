# Runbook

**DLQ is growing.** `python -m engintel.cli quality` shows each message's error. Parse errors =
bad file (fix or remove the upload). Retryable errors = downstream outage; fix it, then re-publish
the payload URIs (`ingest_folder` on the affected files).

**Ingestion stuck / backfill crashed.** Re-run `backfill(uris, same_run_id)`; it resumes from the
`checkpoints` table. Reprocessing already-done items is safe (content hash → `skipped_duplicate`).

**Retrieval quality dropped.** Run `make eval` and compare with `evals/results/latest.json` from the
last good run. Check `chunks.embedding_model` is uniform (mixed models = rebuild with `make index`).

**Quality checks failing.** `make ingest` then look at failed checks. File-level failures mean
the export format changed; row-level failures mean source-system data issues to report upstream.

**Roll back.** Data: re-run ingest from the last good CSV drop (upserts are idempotent).
Code: revert the commit; CI eval gate must pass before deploy.
