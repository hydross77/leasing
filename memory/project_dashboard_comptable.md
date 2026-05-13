---
name: project_dashboard_comptable
description: Dashboard Streamlit pour validation comptable HESS — remplace l'envoi de mails de validation (ADR-013 révisée, ADR-016)
metadata:
  type: project
---

Le comptable HESS valide **systématiquement** tous les dossiers avant tout envoi mail au vendeur, peu importe le verdict IA (conforme OU non conforme). Pour gérer cette charge à 1000 dossiers/jour, le comptable utilise un **dashboard Streamlit dédié**, pas des emails.

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
- **Phase 3** : ajouter les endpoints `/validation/*` à l'API + table `validations` Supabase (cf SQL dans ADR-016).
- **Phase 5b (nouvelle)** : développer le dashboard Streamlit avant le go en prod. 3-5 jours estimés.
- Aucun mail vendeur ne part de l'API ou de n8n sans passer par le clic "Valider" du dashboard.
- Le `MAIL_RECIPIENT_OVERRIDE` en test continue d'agir : tant qu'on est en dev/staging, les mails vont vers Tiffany même après validation.
- Le dashboard remplace aussi le "dashboard monitoring temps réel" qui était dans le backlog post-MVP — on combine les 2 fonctions.

**Dataset doré généré** : chaque validation produit `anomalies_ajoutees` (faux négatifs IA) et `anomalies_retirees` (faux positifs IA). C'est l'input direct pour itérer sur les prompts Phase 2 et mesurer l'amélioration Phase 4.

**À clarifier ultérieurement** :
- Qui est exactement le "comptable" ? Renzo + Aurélien + Alexandre ? Un service dédié ?
- Auth dashboard : magic link Supabase Auth (gratuit) suffit ou besoin SSO HESS ?
