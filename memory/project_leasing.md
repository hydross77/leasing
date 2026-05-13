---
name: project_leasing
description: Contexte projet — système d'analyse automatique de conformité Leasing Social pour HESS Automobile
metadata:
  type: project
---

**Projet** : refonte de l'analyse de conformité des dossiers Leasing Social HESS. Existant : workflow n8n avec ~15 Code nodes JS, sources de faux positifs nombreuses. Cible : API FastAPI séparée + Supabase + Gemini 2.5 Pro.

**Volumétrie cible** : 1000 dossiers/jour, 10-15 PDFs par dossier.

**Marques gérées** : 10 à 15 marques au total (chiffre confirmé par l'utilisatrice 2026-05-13). Le mapping n8n v1 (N8N.txt) ne couvre actuellement que 8 marques : Fiat, Jeep, Hyundai, Nissan, Opel, Peugeot, Renault, Toyota. Les marques manquantes (Citroën, Volkswagen, Mazda, Suzuki, Dacia, etc.) sont à identifier en Phase 1 à partir du dataset Salesforce. ~55-60 concessions au total.

**Stack figée (ADR 1→10)** : Python 3.12 + FastAPI, Pydantic v2, structlog, Supabase, Gemini 2.5 Pro (extraction), OpenAI GPT-5-mini (vérif+mail), Render (Frankfurt), Sentry.

**Séparation des responsabilités (confirmée par utilisatrice 2026-05-13)** :
- **Salesforce = source de vérité métier UNIQUE** (opportunités, fichiers `NEILON__File__c`, statuts, dates de livraison). On lit et on écrit dans SF, jamais on ne duplique la donnée métier ailleurs.
- **n8n = orchestration / flux général** (schedule trigger, lecture SF, verrouillage anti-doublon, appel API, envoi Gmail, update SF final).
- **Code projet (ce repo) = backend métier** (extraction PDF en RAM, prompts par couple marque/concession, vérification ASP 2025, calcul indice confiance, génération HTML mail).
- **Supabase = stockage TECHNIQUE uniquement** (prompts versionnés éditables à chaud, historique d'analyses pour monitoring, mapping concessions). Aucune donnée client/PDF.

**Statut au 2026-05-13** : Phase 0 inachevée (docs créées, mais pas encore de structure FastAPI, Supabase, Render, ni repo Git). Phase 1 lancée en parallèle pour extraction du dataset.

**Why:** L'utilisatrice a demandé de lancer la Phase 1 même si Phase 0 n'est pas 100% finie, en intégrant les retours du PDF d'amélioration.

**How to apply:** Quand on évoque "Phase 1", c'est l'extraction des dossiers gagnés Salesforce sur 12 mois pour rétro-ingénierie des prompts. Les credentials Salesforce ne sont pas encore en place — préparer des scripts prêts mais ne pas tenter d'appels réels sans confirmation.
