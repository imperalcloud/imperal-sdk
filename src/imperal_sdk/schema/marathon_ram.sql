-- ============================================================================
-- IMPERAL CLOUD OS — TENANT VAULT WORKING RAM (COGNITIVE BLACKBOARD)
-- RFC: ICNLI V17
-- ============================================================================

-- 1. Target System Entities (BOM: screens, routes, models, services)
CREATE TABLE IF NOT EXISTS ram_target_entities (
    entity_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    kind TEXT NOT NULL,                -- 'screen' | 'route' | 'model' | 'service' | 'module'
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'core',
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'scaffolded' | 'wired' | 'verified' | 'blocked'
    maturity REAL NOT NULL DEFAULT 0.0,    -- 0.0 to 1.0
    spec_json TEXT NOT NULL DEFAULT '{}',  -- Declarative AST spec extracted from source
    dwell_steps INTEGER NOT NULL DEFAULT 0,-- Steps spent on this entity without maturity change
    dwell_seconds REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ram_entities_project ON ram_target_entities(project_id);
CREATE INDEX IF NOT EXISTS idx_ram_entities_status ON ram_target_entities(status);
CREATE INDEX IF NOT EXISTS idx_ram_entities_kind ON ram_target_entities(kind);

-- 2. Symbol & Contract AST Index (DTOs, signatures, schema definitions)
CREATE TABLE IF NOT EXISTS ram_contracts_index (
    contract_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    entity_id TEXT REFERENCES ram_target_entities(entity_id),
    symbol_name TEXT NOT NULL,
    symbol_type TEXT NOT NULL,        -- 'function' | 'endpoint' | 'table' | 'component'
    input_schema TEXT NOT NULL DEFAULT '{}',
    output_schema TEXT NOT NULL DEFAULT '{}',
    hash_signature TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ram_contracts_proj ON ram_contracts_index(project_id);
CREATE INDEX IF NOT EXISTS idx_ram_contracts_symbol ON ram_contracts_index(symbol_name);

-- 3. Proof-of-Done Registry (Cryptographic/Empirical artifacts)
CREATE TABLE IF NOT EXISTS ram_proof_of_done (
    proof_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    entity_id TEXT REFERENCES ram_target_entities(entity_id),
    verification_type TEXT NOT NULL,  -- 'test_pass' | 'ast_match' | 'http_200' | 'vision_diff'
    evidence_payload TEXT NOT NULL,   -- Test run log, git sha, status code, perceptual diff score
    is_verified INTEGER NOT NULL DEFAULT 1,
    verified_by TEXT NOT NULL DEFAULT 'adversarial_oracle', -- 'adversarial_oracle' | 'pytest' | 'morphometric_vision'
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ram_proof_proj ON ram_proof_of_done(project_id);
CREATE INDEX IF NOT EXISTS idx_ram_proof_entity ON ram_proof_of_done(entity_id);

-- 4. Dynamic Scratchpad & Deferred Blockers (Anti-Yak-Shaving buffer)
CREATE TABLE IF NOT EXISTS ram_blockers_scratchpad (
    blocker_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_entity_id TEXT,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'minor', -- 'minor' | 'blocking' | 'tech_debt'
    status TEXT NOT NULL DEFAULT 'deferred',-- 'deferred' | 'resolving' | 'closed'
    workaround_applied TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. FTS5 Index for Zero-Cost Sub-3ms Semantic Lookups
CREATE VIRTUAL TABLE IF NOT EXISTS ram_search_fts USING fts5(
    entity_id UNINDEXED,
    project_id UNINDEXED,
    name,
    kind,
    category,
    spec_summary,
    content='ram_target_entities',
    content_rowid='rowid'
);
