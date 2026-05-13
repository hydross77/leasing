---
name: project_dashboard_comptable
description: Dashboard Streamlit pour validation comptable HESS — remplace l'envoi de mails de validation (ADR-013 révisée, ADR-016)
metadata:
  type: project
---

Le comptable HESS (Axel) utilise un **dashboard Streamlit dédié comme back-office unique** pour piloter Leasing Social v2. Idéalement, il n'ouvre **jamais** Salesforce directement — toutes les opérations passent par le dashboard, qui synchronise SF en arrière-plan via l'API FastAPI.

Précision 2026-05-13 : le dashboard doit gérer non seulement la validation des verdicts IA, mais aussi :
- Changer `StageName` (1-Nouveau → 4-Gagné → 5-Perdu)
- Override manuel de `Conformite_du_dossier__c`
- Décocher `Tech_Dossier_verifier__c` pour forcer une ré-analyse
- Voir historique, stats, dossiers en retard

**Flow définitif** :

```
Vendeur upload → SF → n8n → API /analyze → écrit en base (statut=en_attente)
                                                  ↓
                                       Dashboard comptable (Streamlit)
                                       - Liste les dossiers en attente
                                       - Permet ajouter/retirer/modifier les anomalies
                                       - Bouton "Valider et envoyer"
                                                  ↓
                                       POST /validation/{id} → n8n → mail vendeur + update SF
```

**Le comptable peut** :
- Confirmer le verdict IA (1 clic)
- Inverser le verdict (faux positif / faux négatif détecté)
- Ajouter une anomalie que l'IA a manquée
- Retirer une anomalie que l'IA a faussement détectée

**Why:** L'utilisatrice (2026-05-13) a proposé cette approche pour deux raisons :
1. Éviter le déluge d'emails de validation (~500/jour) au comptable
2. Couvrir les faux négatifs IA (verdicts conformes potentiellement erronés), pas seulement les faux positifs

**How to apply:**
- **Phase 3** : ajouter les endpoints back-office complets à l'API (`/dossiers/*`, `/stats`, `/validation/*`) + table `validations` Supabase (cf SQL dans ADR-016).
- **Phase 5b** : développer le dashboard Streamlit avant le go en prod. ~5-7 jours estimés (élargi par rapport à l'estimation initiale 3-5 j à cause des fonctions back-office complètes).
- Aucun mail vendeur ne part de l'API ou de n8n sans passer par le clic "Valider" du dashboard.
- Le `MAIL_RECIPIENT_OVERRIDE` en test continue d'agir : tant qu'on est en dev/staging, les mails vont vers Tiffany même après validation.
- Le dashboard combine 3 fonctions : (1) validation des verdicts IA, (2) back-office Salesforce (pilotage StageName + Conformite), (3) monitoring temps réel des stats.
- Streamlit n'appelle JAMAIS Salesforce directement — uniquement via l'API FastAPI (centralisation de la logique métier).
- Endpoints API à exposer : `GET /dossiers`, `GET /dossiers/{id}`, `POST /dossiers/{id}/valider`, `POST /dossiers/{id}/stage`, `POST /dossiers/{id}/conformite`, `POST /dossiers/{id}/relancer`, `GET /stats`.

**Dataset doré généré** : chaque validation produit `anomalies_ajoutees` (faux négatifs IA) et `anomalies_retirees` (faux positifs IA). C'est l'input direct pour itérer sur les prompts Phase 2 et mesurer l'amélioration Phase 4.

**À clarifier ultérieurement** :
- Qui est exactement le "comptable" ? Renzo + Aurélien + Alexandre ? Un service dédié ?
- Auth dashboard : magic link Supabase Auth (gratuit) suffit ou besoin SSO HESS ?
