# Data dictionary

**Training inputs:** fundus images + CSV labels. `Combined ID` in the CSV is unreliable (wrong for about 554 of 921 images), so `combined_id` = image filename stem; the original is kept as `csv_combined_id`.

**dr_screening_results:** result_id, hospital_node_id, patient_hash (SHA-256, salted; never raw ID), eye, image_sha256, model_version, model_stage, prediction, confidence, probabilities, flags, triage, ai_finding, rationale, clinical_context, thumbnail (optional), latency_ms, created_at, review fields (confirmed_grade, decision, reviewer, reviewed_at).

**audit_log:** append-only, each row hashes the previous (genesis = 64 zeros); `/audit/verify` recomputes the chain.

**registry.json:** model_name, version, stage, classes, metrics, artefact sha256, ECDSA signature.
