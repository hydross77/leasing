-- =============================================================
-- Leasing Social — Schéma initial Supabase (Phase 0)
-- =============================================================
-- À exécuter dans l'éditeur SQL de Supabase une fois le projet créé.
-- Tables :
--   1. prompts      — prompts versionnés par couple (marque, concession, type)
--   2. analyses     — historique des analyses (rétention 90 jours)
--   3. concessions  — mapping concession SF → email + métadonnées
--
-- Référence : docs architecture.md + ADR-005 (cascade prompts).
-- =============================================================

-- -------------------------------------------------------------
-- Extensions
-- -------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- =============================================================
-- 1. Table `prompts`
--    Cascade de résolution (cf ADR-005) :
--      (marque, concession, type) → (marque, NULL, type) → ('default', NULL, type)
-- =============================================================

CREATE TABLE IF NOT EXISTS prompts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    marque          TEXT NOT NULL,                  -- 'fiat', 'renault', ..., ou 'default'
    concession      TEXT,                           -- NULL = prompt par défaut pour la marque
    type_prompt     TEXT NOT NULL,                  -- 'extraction_bdc', 'extraction_contrat',
                                                    --  'extraction_pieces_admin', 'verification',
                                                    --  'mail_generation'
    version         INTEGER NOT NULL,               -- incrémental par (marque, concession, type)
    contenu         TEXT NOT NULL,                  -- le prompt complet
    modele          TEXT NOT NULL,                  -- 'gemini-2.5-pro', 'gpt-5-mini', etc.
    actif           BOOLEAN NOT NULL DEFAULT FALSE, -- un seul actif par couple, garanti par index
    notes           TEXT,                           -- changelog libre
    cree_par        TEXT,                           -- email
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT prompts_version_unique UNIQUE (marque, concession, type_prompt, version)
);

-- Un seul prompt actif par couple (marque, concession, type_prompt)
-- COALESCE permet l'unicité même quand concession IS NULL
CREATE UNIQUE INDEX IF NOT EXISTS idx_prompts_actif_unique
    ON prompts (marque, COALESCE(concession, ''), type_prompt)
    WHERE actif = TRUE;

CREATE INDEX IF NOT EXISTS idx_prompts_lookup
    ON prompts (marque, concession, type_prompt, actif);

COMMENT ON TABLE prompts IS
    'Prompts versionnés. Résolution en cascade : (marque, concession) → (marque, NULL) → (default, NULL).';
COMMENT ON COLUMN prompts.marque IS
    'Marque normalisée minuscule (fiat, renault, ...) ou ''default'' pour fallback global.';
COMMENT ON COLUMN prompts.concession IS
    'NULL = prompt par défaut pour la marque. Sinon nom SF exact (ex: ''Fiat Mulhouse'').';


-- =============================================================
-- 2. Table `analyses`
--    Historique d'analyses pour monitoring / debug. Rétention 90 jours.
-- =============================================================

CREATE TABLE IF NOT EXISTS analyses (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id          TEXT NOT NULL,                 -- SF Id (18 chars)
    opportunity_name        TEXT,
    marque                  TEXT,
    concession              TEXT,
    statut                  TEXT NOT NULL,                 -- 'conforme', 'non_conforme',
                                                           --  'erreur_technique', 'aucun_doc'
    indice_confiance        INTEGER,                       -- 0-100
    nb_documents            INTEGER,
    documents_manquants     JSONB,                         -- liste de strings
    anomalies               JSONB,                         -- liste d'objets { criticite, libelle, ... }
    prompts_utilises        JSONB,                         -- {extraction_bdc: uuid, verification: uuid, ...}
    duree_ms                INTEGER,
    cout_estime_eur         NUMERIC(10, 4),
    erreur                  TEXT,                          -- null si OK
    cree_le                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT analyses_statut_valide CHECK (
        statut IN ('conforme', 'non_conforme', 'erreur_technique', 'aucun_doc')
    )
);

CREATE INDEX IF NOT EXISTS idx_analyses_opp
    ON analyses (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_analyses_date
    ON analyses (cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_marque_statut
    ON analyses (marque, statut);

COMMENT ON TABLE analyses IS
    'Historique des analyses. Rétention 90 jours (purge auto à mettre en place).';


-- =============================================================
-- 3. Table `concessions`
--    Mapping concession SF → email diffusion conformité.
--    Seedée depuis scripts/seed_concessions.py (issu du mapping n8n v1).
-- =============================================================

CREATE TABLE IF NOT EXISTS concessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom_salesforce      TEXT UNIQUE NOT NULL,   -- ex: "Fiat Belfort"
    marque              TEXT NOT NULL,          -- normalisée minuscule (ex: "fiat")
    ville               TEXT,
    email_conformite    TEXT NOT NULL,
    emails_cc           JSONB DEFAULT '[]'::jsonb,
    actif               BOOLEAN NOT NULL DEFAULT TRUE,
    notes               TEXT,
    cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_concessions_marque
    ON concessions (marque) WHERE actif = TRUE;
CREATE INDEX IF NOT EXISTS idx_concessions_nom_sf
    ON concessions (nom_salesforce);


-- =============================================================
-- 4. Job de purge auto (rétention 90j) — à activer si extension pg_cron disponible
-- =============================================================
-- Si Supabase Pro avec pg_cron : décommenter pour purge automatique chaque nuit
-- SELECT cron.schedule(
--   'purge-analyses-90j',
--   '0 3 * * *',
--   $$ DELETE FROM analyses WHERE cree_le < now() - INTERVAL '90 days' $$
-- );


-- =============================================================
-- 5. Vérifications post-création
-- =============================================================
-- À exécuter après les CREATE pour s'assurer que tout est OK :
--
--   SELECT count(*) FROM prompts;       -- doit retourner 0 (avant Phase 2)
--   SELECT count(*) FROM analyses;      -- doit retourner 0 (avant Phase 3)
--   SELECT count(*) FROM concessions;   -- doit retourner 0 (avant seed)
--
-- Après seed via scripts/seed_concessions.py :
--   SELECT marque, count(*) FROM concessions GROUP BY marque ORDER BY marque;
--   -- Attendu : 8 marques, ~58 lignes au total (mapping n8n v1)
