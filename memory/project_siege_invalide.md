---
name: project_siege_invalide
description: Règle métier — concession "Siège" = dossier invalide d'office, à exclure partout
metadata:
  type: project
---

Quand `Opportunity.Concession_du_proprietaire__c = 'Siège'`, le dossier est **invalide d'office**. Le Siège HESS n'est pas un point de vente, donc une opportunité Leasing rattachée au Siège est une erreur de saisie côté Salesforce qui ne doit pas être analysée comme un dossier client normal.

**Why:** L'utilisatrice a confirmé le 2026-05-13 lors du test d'extraction Phase 1 (un dossier "Siège" est apparu dans les résultats). Règle simple et tranchée.

**How to apply:**
- **Phase 1 (extract_won_dossiers.py)** : ajouter à la SOQL `AND Concession_du_proprietaire__c != 'Siège'` pour ne pas télécharger ces dossiers.
- **Phase 3 (verification.py)** : règle de filtrage en amont — si `concession == 'Siège'`, retourner directement `verdict = 'non_conforme'` avec anomalie "Concession Siège non éligible — dossier à rattacher à un point de vente".
- **Phase 5 (n8n)** : la SOQL d'orchestration `WHERE Tech_Dossier_verifier__c = FALSE` doit aussi exclure `Siège` pour éviter de gaspiller des tokens IA.
- À garder à l'œil : d'autres concessions "fantômes" pourraient apparaître plus tard (ex: "HESS Direction", "HESS Test"). Si oui, étendre l'exclusion ou créer une liste `CONCESSIONS_INVALIDES`.
