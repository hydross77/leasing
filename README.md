# Leasing Social — Analyse automatique de conformité

API d'analyse automatique des dossiers de **Leasing Social** pour HESS Automobile. Vérifie la conformité réglementaire ASP 2025 de chaque dossier client, génère un verdict structuré et un email de notification.

## En bref

- **Volumétrie cible** : 1000 dossiers/jour
- **Stack** : Python 3.12 + FastAPI + Supabase + Gemini 2.5 Pro + OpenAI
- **Déploiement** : Render (auto-deploy depuis `main`)
- **Source de vérité** : Salesforce (orchestré par n8n)
- **Marques gérées** : 10 à 15 (mapping n8n v1 couvre 8 marques, autres à identifier en Phase 1)

## Démarrage rapide (Windows / PowerShell)

```powershell
# 1. Créer la venv (Python 3.12 requis — Python 3.14 incompatible avec pyiceberg)
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 2. Configurer .env
Copy-Item .env.example .env
# Éditer .env :
#   - Générer DATASET_ENCRYPTION_KEY :
#     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   - Remplir SUPABASE_*, GEMINI_API_KEY, SALESFORCE_*

# 3. Lancer en local
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 4. Tester
Invoke-WebRequest http://localhost:8000/health
```

## Tests, lint, format

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format .
.venv\Scripts\python.exe -m mypy app
```

## Workflow Phase 0 → Phase 1

### Phase 0 — Setup (✅ code local OK, services externes à provisionner)

```powershell
# 1. Créer le schéma Supabase
# Coller le contenu de scripts/migrations/001_init_schema.sql dans l'éditeur SQL Supabase

# 2. Seeder les 58 concessions (mapping n8n v1)
.venv\Scripts\python.exe scripts/seed_concessions.py --dry-run   # vérifier
.venv\Scripts\python.exe scripts/seed_concessions.py             # écrire
```

### Phase 1 — Extraction dataset + analyse exploratoire

Voir [`phase-1-extraction-dataset.md`](phase-1-extraction-dataset.md) pour le détail.

```powershell
# 1. Test sur 5 dossiers pour valider la connexion SF
.venv\Scripts\python.exe scripts/extract_won_dossiers.py --limit 5

# 2. Run complet (12 mois glissants, peut prendre plusieurs heures)
.venv\Scripts\python.exe scripts/extract_won_dossiers.py

# 3. Stats du dataset
.venv\Scripts\python.exe scripts/extract_won_dossiers.py --report

# 4. Analyse exploratoire Gemini (prompt OUVERT, pour rétro-ingénierie)
.venv\Scripts\python.exe scripts/analyze_dataset.py --sample-per-pair 10

# 5. Rédaction manuelle de dossier-formats-par-marque.md à partir du JSONL
#    (matériau d'entrée Phase 2)
```

## Endpoints principaux

- `GET /health` — Healthcheck Render (Phase 0 ✅)
- `POST /analyze` — Analyse complète d'un dossier (Phase 3, à venir)
- `POST /validation/{opportunity_id}` — Validation humaine non_conforme (Phase 5, ADR-013)
- `GET /prompts/{marque}` — Récupère le prompt actif d'une marque (debug, Phase 2+)

## Architecture

Voir [`architecture.md`](architecture.md).

## Roadmap

Voir [`roadmap.md`](roadmap.md) pour l'état d'avancement détaillé.

| Phase | Description | Statut |
|-------|-------------|--------|
| 0 | Cadrage et setup projet | ✅ Code local OK — Supabase/Sentry/Render/Git à provisionner |
| 1 | Extraction dataset dossiers gagnés + analyse exploratoire | ⏳ Scripts prêts, lancement après credentials SF |
| 2 | Construction prompts par couple marque/concession (cascade) | ⏳ |
| 3 | API et règles métier ASP 2025 | ⏳ |
| 4 | Backtesting sur dossiers gagnés | ⏳ |
| 5 | Intégration n8n + déploiement Render + human-in-the-loop | ⏳ |
| 6 | Roll-out progressif en production | ⏳ |

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — Instructions permanentes pour Claude Code
- [`architecture.md`](architecture.md) — Schéma technique détaillé + schéma BDD
- [`decisions.md`](decisions.md) — Décisions architecturales (ADR-001 à ADR-015)
- [`roadmap.md`](roadmap.md) — Phases détaillées avec livrables
- [`glossaire.md`](glossaire.md) — Vocabulaire métier ASP, RFR, BDC, règles 2025
- [`ameliorations-v2.md`](ameliorations-v2.md) — Anomalies v1 à corriger + features PDF v2
- [`phase-0-setup.md`](phase-0-setup.md) — Tâches détaillées Phase 0
- [`phase-1-extraction-dataset.md`](phase-1-extraction-dataset.md) — Tâches détaillées Phase 1

## Décisions clés à retenir

- **ADR-003/004/012** : Salesforce = source de vérité unique. Supabase = stockage technique. Aucun PDF persistant.
- **ADR-005** : prompts par couple `(marque, concession)` avec cascade `(marque, concession) → (marque, NULL) → ('default', NULL)`
- **ADR-013** : mail "non conforme" jamais envoyé à la concession sans validation humaine HESS
- **ADR-014** : renommage IA des pièces uploadées (vendeurs en vrac) — picklist SF post-MVP
- **ADR-015** : ré-analyse automatique quand vendeur redépose un dossier (trigger SF + dédup côté API)

## Sécurité & RGPD

- Aucun PDF stocké sur disque en production (streaming depuis Salesforce uniquement)
- Exception Phase 1 : stockage local **chiffré Fernet** pour analyse exploratoire, purgé après Phase 2
- Logs anonymisés (pas de RFR, CNI, adresse dans les logs)
- Rétention base : 90 jours pour l'historique d'analyse
- Voir [`CLAUDE.md`](CLAUDE.md) section "Contraintes métier critiques"

## Override mails en phase de test

`MAIL_RECIPIENT_OVERRIDE=tiffanydellmann@hessautomobile.com` dans `.env` redirige **tous** les mails (interne + concession) vers cette adresse en dev/staging. Vide en prod.

## Contacts projet

- Pilotage : Tiffany Dellmann (copilote@hessautomobile.com)
- Owner technique : Renzo Di Santolo (renzodisantolo@hessautomobile.com)
- Métier / conformité : Aurélien Pottier, Alexandre Schott
