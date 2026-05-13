# Architecture technique

## Vue d'ensemble

Le système est découpé en **3 couches** pour séparer orchestration, logique métier et données.

```
┌─────────────────────────────────────────────────────────────┐
│                       SALESFORCE                            │
│  (Opportunités Leasing, fichiers NEILON__File__c, statuts)  │
└──────────────────────────┬──────────────────────────────────┘
                           │ OAuth API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                          n8n                                │
│  • Schedule trigger (toutes les 1-2 min)                    │
│  • Lecture des opportunités à traiter                       │
│  • Verrouillage anti-doublon (flag SF)                      │
│  • Appel API FastAPI par lot                                │
│  • Routage email selon verdict                              │
│  • Mise à jour Salesforce final                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS POST /analyze
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  API FastAPI (Render)                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  /analyze {opportunity_id, marque, files: [urls]}    │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 ▼                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 1. Charger prompt actif (marque) depuis Supabase     │  │
│  │ 2. Pour chaque PDF : stream depuis URL → Gemini Pro  │  │
│  │ 3. Agréger les extractions                           │  │
│  │ 4. Vérifier conformité (règles ASP 2025 en Python)   │  │
│  │ 5. Calculer indice de confiance                      │  │
│  │ 6. Générer HTML email                                │  │
│  │ 7. Logger l'analyse en base                          │  │
│  │ 8. Retourner verdict structuré                       │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
   ┌────────────────┐            ┌────────────────┐
   │  Supabase      │            │   Sentry       │
   │  (Postgres)    │            │ (monitoring)   │
   │                │            └────────────────┘
   │ • prompts      │
   │ • analyses     │
   │ • concessions  │
   └────────────────┘
```

## Pourquoi cette architecture

### Pourquoi sortir la logique de n8n ?

n8n est excellent pour l'**orchestration** (trigger, connecteurs, routage simple), mais devient un piège dès qu'on a :
- Du parsing complexe (JSON IA, PDF)
- Des règles métier nombreuses et critiques
- Du besoin de tests automatisés
- Du versioning Git propre

Le workflow actuel (avant refonte) a ~15 Code nodes avec du JS difficilement maintenable, pas de tests, et un risque réel de valider à tort un dossier.

### Pourquoi Supabase et pas Salesforce pour les prompts ?

Salesforce est la **source de vérité métier** (opportunités, clients, dossiers). On ne pollue pas son schéma avec de la technique. Supabase héberge :
- Les **prompts versionnés** (édition à chaud sans redéploiement)
- L'**historique des analyses** (pour monitoring, pas pour le métier)
- Le **mapping concessions** (technique, change fréquemment)

### Pourquoi pas de stockage PDF ?

RGPD + simplicité. Les PDFs contiennent CNI, RFR, RIB → données sensibles. Le streaming depuis presigned URLs Salesforce permet :
- Aucune persistance, donc aucun risque
- Aucun coût de stockage
- Salesforce reste la seule source

Contrepartie : si Gemini timeout, on doit re-télécharger pour retry. Acceptable.

## Schéma BDD (Supabase)

### Table `prompts`

Stocke les prompts versionnés par couple `(marque, concession, type_prompt)`.

```sql
CREATE TABLE prompts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  marque          TEXT NOT NULL,                 -- 'fiat', 'hyundai', 'renault', ... ou 'default'
  concession      TEXT,                          -- NULL = prompt par défaut pour la marque ; sinon nom SF exact (ex: 'Fiat Mulhouse')
  type_prompt     TEXT NOT NULL,                 -- 'extraction_bdc', 'extraction_contrat', 'extraction_pieces_admin', 'verification', 'mail_generation'
  version         INTEGER NOT NULL,              -- incrémental par (marque, concession, type_prompt)
  contenu         TEXT NOT NULL,                 -- le prompt complet
  modele          TEXT NOT NULL,                 -- 'gemini-2.5-pro', 'gpt-5-mini', etc.
  actif           BOOLEAN NOT NULL DEFAULT FALSE,
  notes           TEXT,                          -- changelog libre
  cree_par        TEXT,                          -- email
  cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (marque, concession, type_prompt, version)
);

-- Index "actif" — un seul actif par couple (marque, concession, type_prompt)
CREATE UNIQUE INDEX idx_prompts_actif_unique
  ON prompts (marque, COALESCE(concession, ''), type_prompt)
  WHERE actif = TRUE;
```

**Règle de résolution au chargement (cascade)** : pour un dossier de concession `C` (marque `M`, type `T`), on cherche dans cet ordre :

1. `(marque=M, concession=C, type_prompt=T, actif=true)` — surcharge concession spécifique
2. `(marque=M, concession=NULL, type_prompt=T, actif=true)` — fallback marque
3. `(marque='default', concession=NULL, type_prompt=T, actif=true)` — fallback global

**Le fallback global `default` est toujours présent**. Si une marque n'est pas (encore) couverte par un prompt dédié (ex: nouvelle marque ajoutée chez HESS, ou marque détectée hors mapping connu), on tombe automatiquement sur le `default` plutôt que de planter. Aucun dossier ne sort de l'API sans prompt résolu.

**Exemple** : analyse d'un BDC pour "Fiat Mulhouse"

| Cas | Prompts en base | Résolution |
|-----|-----------------|------------|
| Mulhouse a son propre BDC | `(fiat, Fiat Mulhouse, extraction_bdc)` actif | → Étape 1 (surcharge concession) |
| Pas de surcharge concession | `(fiat, NULL, extraction_bdc)` actif | → Étape 2 (prompt marque Fiat) |
| Marque inconnue (ex: Citroën) | seulement `(default, NULL, extraction_bdc)` actif | → Étape 3 (prompt générique) |
| Aucun prompt trouvé | aucun match | → erreur 500 explicite + Sentry alert |

Cette cascade permet de démarrer avec **un prompt par marque** (Phase 2) et de spécialiser ponctuellement une concession sans dupliquer 58 prompts si seules quelques concessions ont un BDC différent.

**Changer de version** : créer une nouvelle ligne avec `version + 1` et basculer `actif` via transaction (toggle atomique).

### Table `analyses`

Historique d'analyses pour monitoring et debugging.

```sql
CREATE TABLE analyses (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id          TEXT NOT NULL,                 -- SF Id (18 chars)
  opportunity_name        TEXT,
  marque                  TEXT,
  concession              TEXT,
  statut                  TEXT NOT NULL,                 -- 'conforme', 'non_conforme', 'erreur_technique', 'aucun_doc'
  indice_confiance        INTEGER,                       -- 0-100
  nb_documents            INTEGER,
  documents_manquants     JSONB,                         -- liste de strings
  anomalies               JSONB,                         -- liste d'objets
  prompts_utilises        JSONB,                         -- {extraction: uuid, verification: uuid, ...}
  duree_ms                INTEGER,
  cout_estime_eur         NUMERIC(10, 4),
  erreur                  TEXT,                          -- null si OK
  cree_le                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_analyses_opp ON analyses (opportunity_id);
CREATE INDEX idx_analyses_date ON analyses (cree_le DESC);
CREATE INDEX idx_analyses_marque_statut ON analyses (marque, statut);
```

**Rétention** : 90 jours, purge auto via job Supabase ou Render cron.

### Table `concessions`

Mapping concession SF → email de diffusion + métadonnées.

```sql
CREATE TABLE concessions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nom_salesforce      TEXT UNIQUE NOT NULL,   -- ex: "Fiat Belfort"
  marque              TEXT NOT NULL,          -- ex: "fiat"
  ville               TEXT,
  email_conformite    TEXT NOT NULL,
  emails_cc           JSONB,                  -- liste de strings (chefs des ventes, etc.)
  actif               BOOLEAN NOT NULL DEFAULT TRUE,
  cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
  modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_concessions_marque ON concessions (marque) WHERE actif = TRUE;
```

## Flux détaillé d'une analyse

### 1. Réception requête n8n

```http
POST /analyze
Content-Type: application/json
Authorization: Bearer <token>

{
  "opportunity_id": "0061x000ABC123XYZ",
  "opportunity_name": "OPP-2026-12345",
  "concession": "Fiat Belfort",
  "files": [
    {
      "id": "a0X1x000000abc",
      "name": "BDC_signe.pdf",
      "url": "https://...presigned...",
      "mime_type": "application/pdf"
    },
    ...
  ]
}
```

### 2. Extraction par PDF

Pour chaque fichier :
1. Détecter la marque depuis `concession` (premier mot, normalisé)
2. Charger prompt actif d'extraction pour cette marque depuis Supabase
3. Stream le PDF depuis l'URL (httpx async)
4. Envoyer à Gemini 2.5 Pro avec le prompt
5. Valider la réponse contre le schéma Pydantic `DocumentExtraction`
6. Si erreur : retry 2x avec backoff, puis fallback "extraction échouée"

Parallélisation : `asyncio.gather` sur tous les PDFs d'un dossier (limite à 5 simultanés pour ne pas saturer Gemini).

### 3. Vérification de conformité

Code Python pur (pas d'IA), testé unitairement. Vérifie les règles ASP 2025 :
- Identité valide
- RFR/part ≤ 16 300 €
- Aide ≤ 27 % TTC
- Géoportail mode "Plus court"
- etc.

Retourne `VerificationResult` : `dossier_valide`, `anomalies`, `documents_manquants`, `documents_valides`.

### 4. Calcul indice de confiance

```python
indice = (documents_conformes / total_documents_attendus) * 100
if anomalies_critiques:
    indice = min(indice, 50)
```

### 5. Génération HTML mail

Templates Jinja2 selon la charte HESS (navy + doré). Deux templates : `mail_conforme.html`, `mail_non_conforme.html`.

### 6. Logging en base

Insertion dans `analyses` avec tous les détails.

### 7. Réponse à n8n

```json
{
  "verdict": "non_conforme",
  "indice_confiance": 67,
  "anomalies": ["Géoportail en mode 'Plus rapide' — non conforme", ...],
  "documents_manquants": ["RIB"],
  "documents_valides": ["CNI", "Permis de conduire", ...],
  "mail": {
    "sujet": "Dossier non conforme – OPP-2026-12345",
    "html": "<!doctype html>...",
    "destinataire_principal": "renzodisantolo@hessautomobile.com",
    "cc": ["aurelienpottier@...", "alexandreschott@..."],
    "concession_mail": "fiatbelfortconformite@hessautomobile.com"
  },
  "salesforce_update": {
    "Tech_Dossier_verifier__c": true,
    "Conformite_du_dossier__c": "Document absent ou à corriger",
    "Date_livraison_definitive__c": "2026-06-15"
  },
  "analyse_id": "uuid-pour-trace"
}
```

n8n se charge ensuite d'envoyer les mails et de patcher Salesforce.

## Robustesse

### Idempotence
Chaque requête `/analyze` est idempotente. Si n8n rejoue par erreur, on relance l'analyse et on insère une nouvelle ligne dans `analyses` (avec le même `opportunity_id`). C'est traçable.

### Gestion de la concurrence
L'API peut traiter N requêtes en parallèle (uvicorn workers). La parallélisation interne par dossier est limitée à 5 PDFs simultanés vers Gemini.

### Retries
- **Gemini** : 2 retries avec backoff exponentiel (1s, 4s), timeout 90s
- **OpenAI** : 2 retries, timeout 30s
- **Supabase** : 3 retries pour les écritures (connection drops)

### Sécurité par défaut
Si une étape critique échoue (extraction, vérification), le verdict par défaut est `erreur_technique` → traitement manuel. **Jamais de validation par défaut**.

## Déploiement Render

- **Service** : Web Service Python
- **Build command** : `pip install -e .`
- **Start command** : `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
- **Env vars** : configurées dans le dashboard Render (secrets)
- **Auto-deploy** : push sur `main` → déploiement
- **Healthcheck** : `/health` toutes les 30s
- **Région** : Frankfurt (latence SF Europe optimale)

## Monitoring

- **Erreurs** : Sentry (toutes les exceptions non gérées + niveau ERROR des logs)
- **Logs applicatifs** : Render UI (structlog JSON, parseable)
- **Métriques métier** : requêtes Supabase ad-hoc + dashboard à construire en Phase 5

## Points d'extension futurs (hors scope MVP)

- Cache Redis pour les analyses récentes (si re-analyse demandée)
- Fine-tuning d'un petit modèle pour pré-classifier le type de document (CNI / BDC / avis impôt) avant Gemini → économie tokens
- Dashboard Streamlit pour superviser en temps réel
- Webhook Salesforce direct (sans n8n) en alternative
