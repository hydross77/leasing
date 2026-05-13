# Phase 0 — Setup initial du projet

> Tâche à exécuter par Claude Code en ouvrant ce fichier dans le projet `leasing`. **Lire `CLAUDE.md` à la racine avant de démarrer.**

## Objectif

Mettre en place la structure du projet FastAPI, les outils de qualité de code, l'infra de base (Supabase, Render, Sentry), et un premier déploiement opérationnel.

À la fin de cette phase, on doit avoir :
- Un endpoint `/health` qui répond `200 OK` en local **et** en prod sur Render
- Une base Supabase avec les 3 tables créées
- Un repo Git proprement initialisé sur GitHub
- Sentry connecté
- Une stack de dev fluide (ruff, mypy, pytest, structlog)

---

## Étape 1 — Initialisation du projet Python

### 1.1 Créer la structure de dossiers

```
leasing/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   └── health.py
│   │   └── dependencies.py
│   ├── core/
│   │   └── __init__.py
│   ├── models/
│   │   └── __init__.py
│   ├── services/
│   │   └── __init__.py
│   ├── prompts/
│   │   └── __init__.py
│   └── utils/
│       ├── __init__.py
│       └── logging.py
├── scripts/
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── __init__.py
│   └── integration/
│       └── __init__.py
├── .env.example
├── .gitignore
├── pyproject.toml
├── ruff.toml
└── README.md (déjà présent)
```

### 1.2 `pyproject.toml`

Utiliser `pyproject.toml` comme source unique de configuration (PEP 621 + outils).

Dépendances runtime minimales pour cette phase :
- `fastapi`
- `uvicorn[standard]`
- `pydantic[email]`
- `pydantic-settings`
- `httpx`
- `structlog`
- `sentry-sdk[fastapi]`
- `supabase` (client officiel)
- `python-dotenv`

Dépendances dev :
- `ruff`
- `mypy`
- `pytest`
- `pytest-asyncio`
- `pytest-cov`
- `httpx` (pour TestClient)

Python : `>=3.12`.

Configurer également les sections `[tool.pytest.ini_options]`, `[tool.mypy]`, et `[project.optional-dependencies]` pour avoir `pip install -e ".[dev]"`.

### 1.3 `ruff.toml`

Config ruff stricte :
- `line-length = 100`
- Activer `E`, `F`, `W`, `I` (isort), `B` (bugbear), `UP` (pyupgrade), `N` (pep8-naming)
- Cible : Python 3.12

### 1.4 `.gitignore`

Standard Python + secrets :
- `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `.env`, `.env.local`
- `*.pdf`, `*.png`, `*.jpg` (sécurité : éviter de commiter un dossier client par erreur)
- `dataset/`, `downloads/` (dossiers de la Phase 1)
- `.coverage`, `htmlcov/`
- `.vscode/`, `.idea/`

### 1.5 `.env.example`

Lister toutes les variables d'environnement nécessaires, sans valeurs réelles :

```
# Environnement
ENV=dev
LOG_LEVEL=INFO

# Auth API (token partagé avec n8n)
API_TOKEN=changeme

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# IA
GEMINI_API_KEY=
OPENAI_API_KEY=

# Sentry
SENTRY_DSN=

# Salesforce (si l'API les appelle directement — sinon n8n)
SALESFORCE_CLIENT_ID=
SALESFORCE_CLIENT_SECRET=
SALESFORCE_USERNAME=
SALESFORCE_PASSWORD=
SALESFORCE_TOKEN=
SALESFORCE_DOMAIN=login
```

---

## Étape 2 — Configuration applicative

### 2.1 `app/config.py`

Settings basé sur `pydantic-settings`. Chargement automatique depuis `.env` en dev, depuis l'env Render en prod. Validation stricte au démarrage.

Champs minimaux pour cette phase :
- `env: Literal["dev", "staging", "prod"]`
- `log_level: str`
- `api_token: str` (sera requis sur les endpoints sensibles plus tard)
- `supabase_url: str`
- `supabase_key: str`
- `sentry_dsn: str | None`

Exposer via une fonction `get_settings()` cachée avec `@lru_cache`.

### 2.2 `app/utils/logging.py`

Configurer structlog en mode JSON. Format de chaque log :
```json
{"event": "dossier_analyse", "level": "info", "timestamp": "...", "opportunity_id": "...", "duree_ms": 1234}
```

Fonction `setup_logging(level)` appelée au démarrage de l'app.

### 2.3 `app/main.py`

Création de l'app FastAPI :
- Titre, version, description (lisible dans `/docs`)
- Inclusion du router `health`
- Setup Sentry si DSN présent
- Setup logging au démarrage (`@app.on_event("startup")` ou lifespan moderne)
- Middleware basique de logging des requêtes (méthode, path, durée, status)

### 2.4 `app/api/routes/health.py`

Un endpoint simple :
```python
GET /health
```
Retour : `{"status": "ok", "env": "dev", "version": "0.1.0"}`. Pas d'authentification requise.

---

## Étape 3 — Tests minimaux

### 3.1 `tests/unit/test_health.py`

Tester que `/health` répond bien :
- Status 200
- JSON contient `"status": "ok"`

Utiliser `TestClient` de FastAPI.

### 3.2 Vérifier que `pytest` passe

```bash
pytest
```

Doit afficher 1 test passé.

---

## Étape 4 — Outils qualité

Vérifier que ces commandes passent sans erreur sur le code généré :

```bash
ruff check .
ruff format .
mypy app
pytest
```

Si erreurs : corriger avant de continuer.

---

## Étape 5 — Initialisation Git + GitHub

### 5.1 Init local

```bash
git init
git add .
git commit -m "chore: initial project setup (phase 0)"
```

### 5.2 Création du repo GitHub

**À faire manuellement par Renzo** :
1. Créer un repo privé sur GitHub : `leasing` (ou `hess-leasing-social`)
2. Connecter le repo local :
```bash
git branch -M main
git remote add origin <url>
git push -u origin main
```

Puis demander à Claude Code de continuer après le push.

---

## Étape 6 — Provisionning Supabase

**À faire manuellement par Renzo** :

1. Créer un compte sur https://supabase.com (si pas déjà fait)
2. Créer un projet `leasing-prod` (ou similaire), région Frankfurt
3. Récupérer dans Settings → API :
   - Project URL
   - `anon` ou `service_role` key (le `service_role` pour l'API serveur)
4. Mettre ces valeurs dans `.env` local

### 6.1 Créer les tables

Dans l'éditeur SQL Supabase, exécuter les `CREATE TABLE` documentés dans `docs/architecture.md` section "Schéma BDD" :
- `prompts`
- `analyses`
- `concessions`

Vérifier avec une requête simple :
```sql
SELECT * FROM prompts LIMIT 1;  -- doit retourner 0 lignes mais sans erreur
SELECT * FROM analyses LIMIT 1;
SELECT * FROM concessions LIMIT 1;
```

### 6.2 Seed initial du mapping concessions

Insérer les 55 concessions à partir du mapping JS actuel (dans le node `Mapping concession` du workflow n8n).

Claude Code peut générer un script `scripts/seed_concessions.py` qui :
1. Lit un dictionnaire en dur (le mapping copié du JS)
2. Insère chaque ligne dans la table `concessions` via le client Supabase
3. Est idempotent (UPSERT sur `nom_salesforce`)

Lancer le script une fois pour seeder.

---

## Étape 7 — Sentry

**À faire manuellement par Renzo** :

1. Créer un compte sur https://sentry.io (free tier OK)
2. Créer un projet Python (FastAPI)
3. Copier le DSN
4. Mettre dans `.env` local et dans les env vars Render

### 7.1 Vérifier l'intégration

Ajouter temporairement une route de test qui throw une exception :
```python
@app.get("/debug-sentry")
def debug_sentry():
    raise Exception("Test Sentry")
```

Appeler en local, vérifier que l'erreur apparaît dans Sentry. **Supprimer la route ensuite.**

---

## Étape 8 — Setup Render

**À faire manuellement par Renzo** :

1. Créer un compte sur https://render.com
2. Connecter GitHub
3. New → Web Service → sélectionner le repo `leasing`
4. Configuration :
   - **Region** : Frankfurt
   - **Branch** : `main`
   - **Runtime** : Python
   - **Build command** : `pip install -e .`
   - **Start command** : `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
   - **Instance type** : Starter (~7 €/mois) ou Free pour démarrer
5. Env vars : ajouter toutes les variables du `.env` (sauf en valeurs prod : générer un vrai `API_TOKEN`, mettre les clés Supabase et Sentry réelles)

### 8.1 Vérifier le déploiement

Au push sur `main`, Render doit auto-déployer. À la fin :
- L'URL Render (`https://leasing-xxx.onrender.com/health`) doit répondre `{"status": "ok", "env": "prod", ...}`

---

## Étape 9 — Validation finale Phase 0

Checklist finale :

- [ ] `pytest`, `ruff check`, `mypy app` passent en local
- [ ] `/health` répond OK en local (`uvicorn app.main:app --reload`)
- [ ] Repo poussé sur GitHub
- [ ] Supabase opérationnel, 3 tables créées, concessions seedées
- [ ] Sentry reçoit bien une erreur test (puis route de test supprimée)
- [ ] Render déployé, `/health` accessible publiquement
- [ ] Cocher l'avancement dans `docs/roadmap.md` section Phase 0

Quand tout est vert : commit final `chore: phase 0 setup complete`, et on enchaîne sur la Phase 1.

---

## Notes pour Claude Code

- **Ne PAS** créer de logique métier (extraction, vérification) dans cette phase. C'est uniquement du setup.
- **Demander confirmation** avant de pousser sur `main` (le push déclenche un auto-deploy Render).
- **Mettre à jour** `docs/roadmap.md` au fur et à mesure pour cocher les items terminés.
- Si une étape "manuelle Renzo" bloque (compte à créer, secret à fournir), s'arrêter et demander explicitement plutôt que d'inventer.
