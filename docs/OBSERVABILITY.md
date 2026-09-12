# Observability

OpenTelemetry instruments FastAPI. Production logs/traces must carry `request_id`, `job_id`, `analysis_id`, `repository_id`, and `snapshot_id` as opaque metadata, never source, patches, prompts, credentials, or snippets.

Result metrics currently record analysis duration, files analyzed, symbols indexed, graph nodes/edges, changed files, candidate/confirmed impacts, risks, test gaps, and LLM call/failure counts. Queue and worker duration require explicit RQ instrumentation in the next hardening pass.

Alert on terminal failure rate, queue age, latency, evidence verification failure, parser degradation, and anomalous LLM token usage. Exporters are deployment configuration; instrumentation alone is not an operational dashboard.
