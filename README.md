# Leasing Social — Analyse automatique de conformité

API d'analyse automatique des dossiers de **Leasing Social** pour HESS Automobile. Vérifie la conformité réglementaire ASP 2025 de chaque dossier client, génère un verdict structuré et un email de notification.

## En bref

- **Volumétrie cible** : 1000 dossiers/jour
- **Stack** : Python 3.12 + FastAPI + Supabase + Gemini 2.5 Pro + OpenAI
- **Déploiement** : Render (auto-deploy depuis `main`)
- **Source de vérité** : Salesforce (orchestré par n8n)

## Démarrage rapide

```bash
# 1. Cloner et installer
git clone <repo>
cd leasing
python -m venv .venv
source .venv/bin/activate   # ou .venv\Scripts\activate sous Windows
pip install -e ".[dev]"

# 2. Configurer
cp .env.example .env
# Éditer .env avec les vraies clés

# 3. Lancer en local
uvicorn app.main:app --reload --port 8000

# 4. Tester
curl http://localhost:8000/health
```

## Endpoints principaux

- `POST /analyze` — Analyse complète d'un dossier (appelé par n8n)
- `GET /health` — Healthcheck Render
- `GET /prompts/{marque}` — Récupère le prompt actif d'une marque (debug)

## Architecture

Voir [`docs/architecture.md`](docs/architecture.md).

## Roadmap

Voir [`docs/roadmap.md`](docs/roadmap.md) pour l'état d'avancement détaillé.

| Phase | Description | Statut |
|-------|-------------|--------|
| 0 | Cadrage et setup projet | 🚧 En cours |
| 1 | Extraction dataset dossiers gagnés + analyse exploratoire | ⏳ |
| 2 | Construction prompts par marque | ⏳ |
| 3 | API et règles métier ASP 2025 | ⏳ |
| 4 | Backtesting sur dossiers gagnés | ⏳ |
| 5 | Intégration n8n + déploiement Render | ⏳ |
| 6 | Roll-out progressif en production | ⏳ |

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — Instructions permanentes pour Claude Code
- [`docs/architecture.md`](docs/architecture.md) — Schéma technique détaillé
- [`docs/decisions.md`](docs/decisions.md) — Décisions architecturales (ADR)
- [`docs/roadmap.md`](docs/roadmap.md) — Phases détaillées avec livrables
- [`docs/glossaire.md`](docs/glossaire.md) — Vocabulaire métier (ASP, RFR, BDC, etc.)
- [`tasks/`](tasks/) — Tâches détaillées prêtes pour Claude Code

## Tests

```bash
pytest                          # Tous les tests
pytest tests/unit               # Tests unitaires uniquement
pytest -k verification          # Tests règles métier
pytest --cov=app                # Avec coverage
```

## Lint / Format / Type-check

```bash
ruff check .                    # Lint
ruff format .                   # Format
mypy app                        # Type-check
```

## Contribution

1. Brancher : `git checkout -b feat/ma-feature`
2. Coder + tests
3. `ruff check . && ruff format . && mypy app && pytest`
4. Commit : `git commit -m "feat: description"`
5. PR vers `main`

## Sécurité & RGPD

- Aucun PDF stocké sur disque (streaming depuis Salesforce uniquement)
- Logs anonymisés (pas de RFR, CNI, adresse dans les logs)
- Rétention base : 90 jours pour l'historique d'analyse
- Voir [`CLAUDE.md`](CLAUDE.md) section "Contraintes métier critiques"

## Contacts projet

- Owner technique : Renzo Di Santolo (renzodisantolo@hessautomobile.com)
- Métier / conformité : Aurélien Pottier, Alexandre Schott
