-- =============================================================
-- Migration 002 — Table `validations` (ADR-013 + ADR-016)
-- =============================================================
-- À exécuter dans l'éditeur SQL Supabase APRÈS 001_init_schema.sql.
-- Stocke chaque validation comptable effectuée depuis le dashboard.
-- =============================================================

CREATE TABLE IF NOT EXISTS validations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analyse_id          UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    opportunity_id      TEXT NOT NULL,
    statut              TEXT NOT NULL,
    decision_comptable  TEXT,                         -- 'confirme_ia' | 'inverse_ia' | 'modifie' | 'refus_office_auto'
    anomalies_finales   JSONB NOT NULL DEFAULT '[]'::jsonb,
    anomalies_ajoutees  JSONB DEFAULT '[]'::jsonb,    -- ce que l'IA a raté (faux négatif)
    anomalies_retirees  JSONB DEFAULT '[]'::jsonb,    -- faux positifs IA retirés par le comptable
    comptable_email     TEXT,                         -- email Google de la personne qui a validé
    notes               TEXT,
    cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    valide_le           TIMESTAMPTZ,
    CONSTRAINT validations_statut_valide CHECK (
        statut IN (
            'en_attente',
            'validee_conforme',
            'validee_non_conforme',
            'refus_office'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_validations_analyse ON validations (analyse_id);
CREATE INDEX IF NOT EXISTS idx_validations_opp ON validations (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_validations_comptable ON validations (comptable_email);
CREATE INDEX IF NOT EXISTS idx_validations_statut ON validations (statut);

COMMENT ON TABLE validations IS
    'Décisions comptable depuis le dashboard. Alimente la boucle d''amélioration des prompts.';
COMMENT ON COLUMN validations.anomalies_ajoutees IS
    'Anomalies que l''IA n''a pas détectées et que le comptable a ajoutées (faux négatifs).';
COMMENT ON COLUMN validations.anomalies_retirees IS
    'Anomalies remontées par l''IA mais incorrectes (faux positifs) retirées par le comptable.';
