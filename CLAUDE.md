# CLAUDE.md — Instructions permanentes pour Claude Code

> Ce fichier est lu par Claude Code à chaque session. Il contient le contexte, les conventions et les contraintes du projet.

## Contexte du projet

Système d'analyse automatique de conformité pour les dossiers **Leasing Social** (aide d'État à la location longue durée de véhicules électriques) de **HESS Automobile**, groupe de concessions automobiles.

**Volumétrie cible** : 1000 dossiers/jour, dont beaucoup avec 10-15 PDFs (BDC, contrat de location, CNI, permis, avis d'imposition, justificatif domicile, géoportail, photos véhicule, attestations diverses).

**Objectif** : analyser chaque dossier reçu sur Salesforce, vérifier la conformité réglementaire ASP 2025, notifier la concession et le client interne, mettre à jour Salesforce avec le verdict.

## Architecture cible

```
┌─────────────────┐   ┌─────────────────┐   ┌──────────────────┐
│   Salesforce    │   │      n8n        │   │  API FastAPI     │
│  (source vérité)│◄──┤  (orchestration)├──►│  (logique métier)│
└─────────────────┘   └─────────────────┘   └────────┬─────────┘
                              │                       │
                              ▼                       ▼
                      ┌──────────────┐        ┌──────────────┐
                      │    Gmail     │        │  Supabase    │
                      │ (envoi mail) │        │ (Postgres)   │
                      └──────────────┘        └──────────────┘
                                                      │
                                              ┌───────┴────────┐
                                              ▼                ▼
                                       ┌──────────┐     ┌──────────┐
                                       │  Gemini  │     │  OpenAI  │
                                       │   2.5    │     │  GPT-5   │
                                       └──────────┘     └──────────┘
```

**Séparation des responsabilités** :
- **n8n** : trigger schedule, connecteurs Salesforce/Gmail, orchestration haut niveau, verrouillage anti-doublon
- **API FastAPI (ce projet)** : téléchargement PDFs, prompts dynamiques par marque, extraction IA, règles métier, calcul indice de confiance, génération HTML email
- **Supabase** : prompts versionnés éditables à chaud, historique des analyses, mapping concessions
- **Salesforce** : source de vérité métier (opportunités, fichiers, statuts)

## Stack technique

- **Langage** : Python 3.12+
- **Framework** : FastAPI + Uvicorn
- **Validation** : Pydantic v2 (modèles stricts pour entrées/sorties IA)
- **HTTP client** : httpx (async)
- **PDF** : pdfplumber pour le texte, pypdf pour les manipulations, Pillow pour les images
- **BDD** : Supabase (PostgreSQL) via supabase-py ou asyncpg directement
- **IA** : google-generativeai (Gemini 2.5 Pro) + openai (GPT-4/GPT-5)
- **Tests** : pytest + pytest-asyncio
- **Lint/Format** : ruff (lint + format en un)
- **Type-check** : mypy (mode strict sur les modules core)
- **Logging** : structlog (JSON structuré pour parsing facile)
- **Monitoring** : Sentry (erreurs) + logs Render natifs
- **Déploiement** : Render (auto-deploy depuis GitHub main)

## Conventions de code

### Structure de dossiers

```
leasing/
├── app/
│   ├── __init__.py
│   ├── main.py                  # Entrée FastAPI
│   ├── config.py                # Settings Pydantic (env vars)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── analyze.py       # POST /analyze
│   │   │   └── health.py        # GET /health
│   │   └── dependencies.py
│   ├── core/
│   │   ├── extraction.py        # Appels Gemini
│   │   ├── verification.py      # Règles métier ASP 2025
│   │   ├── confidence.py        # Calcul indice de confiance
│   │   └── mail_html.py         # Génération HTML email HESS
│   ├── models/
│   │   ├── salesforce.py        # Pydantic des entités SF
│   │   ├── document.py          # Pydantic du résultat d'extraction
│   │   ├── verification.py      # Pydantic du verdict
│   │   └── prompts.py           # Pydantic des prompts en base
│   ├── services/
│   │   ├── salesforce.py        # Client SF (lecture/écriture)
│   │   ├── gemini.py            # Wrapper Gemini avec retry
│   │   ├── openai_client.py     # Wrapper OpenAI
│   │   ├── supabase_client.py   # Wrapper Supabase
│   │   └── pdf_loader.py        # Téléchargement + extraction PDF
│   ├── prompts/
│   │   └── loader.py            # Charge prompt actif par marque depuis Supabase
│   └── utils/
│       ├── logging.py
│       └── retry.py
├── scripts/
│   ├── extract_won_dossiers.py  # Extraction dossiers gagnés (Phase 1)
│   ├── analyze_dataset.py       # Analyse exploratoire (Phase 1)
│   └── backtest.py              # Backtesting (Phase 4)
├── tests/
│   ├── unit/
│   │   ├── test_verification.py # Tests règles métier (critique)
│   │   └── test_confidence.py
│   └── integration/
│       └── test_analyze.py
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── roadmap.md
│   └── glossaire.md
├── tasks/                       # Tâches Claude Code détaillées
│   └── phase-0-setup.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── ruff.toml
├── CLAUDE.md                    # CE FICHIER
└── README.md
```

### Style Python

- **Type hints partout**. Pas de fonction sans signature typée.
- **Pydantic** pour toute donnée externe (entrée API, sortie IA, ligne BDD).
- **async/await** par défaut pour I/O (HTTP, BDD, IA). Sync uniquement pour CPU-bound.
- **Pas de globals mutables**. Settings via `app.config.Settings()` injecté.
- **Logging structuré** : `log.info("dossier_analyse", opportunity_id=..., duree_ms=...)`. Jamais de `print`.
- **Pas d'exceptions silencieuses**. Tout `except` doit logger ou re-raise.
- **Imports triés** par ruff (isort intégré).
- **Docstrings** au format Google sur les fonctions publiques.

### Naming

- **Variables et fonctions** : `snake_case` français OU anglais, **cohérent par fichier**. Métier en français (`verifier_conformite`, `extraire_bdc`), technique en anglais (`fetch_pdf`, `parse_response`).
- **Classes Pydantic** : `PascalCase` anglais (`DocumentExtraction`, `VerificationResult`).
- **Constantes** : `SCREAMING_SNAKE_CASE`.

### Gestion des erreurs IA

L'IA peut **toujours** retourner du JSON invalide, halluciner des champs, timeout. Règles strictes :

1. **Validation Pydantic systématique** sur tout retour IA. Si parse fail → retry 2x, puis erreur structurée loggée.
2. **Jamais valider un dossier conforme si l'extraction a échoué**. Comportement par défaut sur erreur = "non conforme + erreur technique" (sécurité).
3. **Toujours logger le prompt + la réponse brute** en cas d'erreur (pour debug).
4. **Timeouts explicites** : 90s pour Gemini Pro, 30s pour OpenAI.

## Contraintes métier critiques

### Risque financier
Un faux positif (dossier non conforme validé à tort) → aide ASP versée à tort → reproche financier à HESS. **La sécurité par défaut est de refuser**.

### Règles ASP 2025 (à ne JAMAIS modifier sans validation)
Voir `docs/glossaire.md` pour le détail. Points critiques :
- RFR / nb de parts ≤ 16 300 €
- Aide ≤ 27 % du prix TTC, plafond 7000 €
- Durée location ≥ 3 ans, ≥ 12 000 km/an
- Loyer < 200 €/mois hors options
- Géoportail en mode **"Plus court"** uniquement (jamais "Plus rapide")
- Si distance domicile-travail < 15 km : géoportail obligatoire
- Pas de mention "Bonus écologique" sur BDC (interdit)

### RGPD
- Aucun PDF stocké sur disque. Streaming depuis presigned URLs Salesforce → analyse en RAM → résultat JSON stocké en base → PDF jeté.
- Les logs ne doivent **jamais** contenir : numéro CNI, RFR, adresse complète, n° permis. Logger uniquement `opportunity_id` + métadonnées techniques.
- Rétention historique d'analyse : 90 jours en base, puis purge automatique.

## Conventions Git

- **Branche principale** : `main`
- **Branches feature** : `feat/nom-court`, `fix/nom-court`, `chore/nom-court`
- **Commits** : format Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`)
- **PR obligatoire** pour merger sur `main` (auto-deploy Render).
- **CI** : ruff + mypy + pytest passent obligatoirement avant merge.

## Comment Claude Code doit travailler

1. **Toujours lire `docs/roadmap.md` et `tasks/`** avant de coder, pour savoir où on en est.
2. **Tâche à la fois**. Ne pas créer 20 fichiers d'un coup. Avancer par incréments testables.
3. **Tests d'abord** sur les règles métier (`app/core/verification.py`). Pas de règle ASP sans test.
4. **Demander confirmation** avant : suppression de fichiers, modification du schéma BDD, changement de dépendance majeure.
5. **Ne jamais inventer** : une règle métier qui n'est pas dans `docs/glossaire.md` se demande, ne se devine pas.
6. **Logger les décisions** dans `docs/decisions.md` quand on fait un choix technique non trivial.
7. **Mettre à jour `docs/roadmap.md`** quand une phase avance (cocher les items terminés).

## Variables d'environnement

Voir `.env.example`. Jamais commiter `.env`. Render utilise des secrets dans son UI.

Variables clés :
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY`
- `SALESFORCE_*` (OAuth pour lecture, si l'API les appelle directement — sinon n8n gère)
- `SENTRY_DSN`
- `LOG_LEVEL` (INFO en prod, DEBUG en dev)
- `ENV` (dev/staging/prod)

## État d'avancement actuel

**Phase 0 — Cadrage** : en cours.

Prochaine étape : suivre `tasks/phase-0-setup.md`.
