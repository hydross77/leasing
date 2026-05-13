---
name: project_typage_pieces_sf
description: Stratégie de typage des pièces uploadées par les concessions — renommage IA d'abord, picklist SF ensuite (ADR-014)
metadata:
  type: project
---

Aujourd'hui les vendeurs / concessions uploadent les pièces en vrac dans `NEILON__File__c` (lié à l'Opportunity), sans aucun champ qui distingue un BDC d'une CNI d'un justificatif de domicile. L'utilisatrice a confirmé le 2026-05-13 que les concessions sont "bourrins" et qu'il n'y a pas de structure de typage côté Salesforce actuel.

**Décision (ADR-014)** :

1. **Court terme (Phase 3, prévu)** : renommage IA via `/analyze`. L'API renvoie `{ file_id: nom_propose }` ; n8n patche `NEILON__File__c.Name`. Aucun changement côté vendeur.

2. **Post-MVP (sujet SF admin, hors API)** : ajouter un champ picklist `Type_document__c` sur `NEILON__File__c`, pré-rempli par l'IA, modifiable par le vendeur. Double validation humain + IA, écart = alerte.

3. **Alternatives écartées** : champs lookup dédiés par type sur Opportunity, sections obligatoires dans le formulaire d'upload SF — trop disruptifs pour un gain marginal.

**Why:** Les concessions n'ont pas la culture de la structure d'upload. Forcer un changement d'UX en plus de la mise en place de l'IA serait un double risque adoption. Mieux : adapter la techno à leur usage actuel.

**How to apply:**
- Phase 3 : implémenter le renommage IA en sortie de `/analyze` (déjà §2.5 du PDF v2, voir [[project_ameliorations_v2]]).
- Ne pas demander à Salesforce admin de créer le picklist tant que le MVP n'est pas en prod stable — on en a pas besoin tant que le renommage IA suffit.
- Si Phase 4 backtest révèle que la classification IA des pièces a un taux d'erreur > 5%, prioriser le picklist plus tôt.
