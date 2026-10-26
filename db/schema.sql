-- PostgreSQL 16 schema for the Madhu-DR hospital-node service (generated from src/preveda_dr/db.py).
-- The service also creates these tables itself on start-up (SQLite or PostgreSQL); use this file for DBA review / migrations.

CREATE TABLE audit_log (
	id SERIAL NOT NULL, 
	ts VARCHAR(40) NOT NULL, 
	actor VARCHAR(100) NOT NULL, 
	action VARCHAR(50) NOT NULL, 
	resource_id VARCHAR(64), 
	details JSON, 
	prev_hash VARCHAR(64) NOT NULL, 
	entry_hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE dr_screening_results (
	result_id VARCHAR(36) NOT NULL, 
	hospital_node_id VARCHAR(50) NOT NULL, 
	patient_hash VARCHAR(64), 
	eye VARCHAR(10), 
	image_sha256 VARCHAR(64) NOT NULL, 
	model_version VARCHAR(50) NOT NULL, 
	model_stage VARCHAR(20), 
	prediction VARCHAR(20) NOT NULL, 
	confidence FLOAT, 
	probabilities JSON, 
	flags JSON, 
	triage VARCHAR(10) NOT NULL, 
	ai_finding TEXT, 
	rationale TEXT, 
	clinical_context JSON, 
	thumbnail BYTEA, 
	latency_ms FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reviewer_id VARCHAR(100), 
	confirmed_grade VARCHAR(40), 
	review_decision VARCHAR(20), 
	review_rationale TEXT, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (result_id)
);
CREATE INDEX ix_dr_results_created ON dr_screening_results (created_at);
CREATE INDEX ix_dr_results_patient ON dr_screening_results (patient_hash);

-- Reserved for the next build step (FRD 13.1.1): human-readable learned patterns for retinopathy
CREATE TABLE IF NOT EXISTS pattern_store (
  pattern_id UUID PRIMARY KEY,
  pattern_type VARCHAR(20),            -- FRAUD / CLINICAL
  pattern_code VARCHAR(20) UNIQUE,     -- e.g. PAT-DR-001
  description TEXT NOT NULL,
  source_hospitals VARCHAR(50)[],
  cases_supporting INTEGER,
  confidence NUMERIC(5,4),
  first_discovered_at TIMESTAMPTZ,
  promoted_to_global_at TIMESTAMPTZ,
  model_version VARCHAR(50),
  is_active BOOLEAN DEFAULT TRUE
);
