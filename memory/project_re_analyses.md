---
name: project_re_analyses
description: Quand le vendeur redépose un dossier corrigé, l'ancien fichier reste dans SF et pollue l'analyse — solution en 3 niveaux (ADR-015)
metadata:
  type: project
---

Problème non traité en v1 : Salesforce ne supprime pas l'ancien `NEILON__File__c` quand un vendeur uploade une version corrigée. Le workflow n8n v1 récupère tous les fichiers de l'opportunité → l'ancien BDC fautif est ré-analysé en même temps que le nouveau → l'anomalie persiste à tort.

**Décision (ADR-015)** : approche en 3 niveaux, démarrer au Niveau 1.

- **Niveau 1 (MVP, Phase 5)** : Trigger SF qui repasse `Tech_Dossier_verifier__c = FALSE` à chaque nouveau fichier. L'API dédup côté Python en gardant le plus récent par `type_document` détecté.
- **Niveau 2 (post-MVP)** : pré-filtrage des fichiers à analyser côté API pour économiser des tokens IA.
- **Niveau 3 (cible)** : champ `Obsolete__c` sur `NEILON__File__c` géré par trigger SF, l'API filtre `Obsolete = FALSE` dans la SOQL.

**Why:** L'utilisatrice (2026-05-13, débutante SF/n8n) a identifié le problème par intuition produit : "si vendeur redépose, ça supprime l'ancien ? l'IA re-vérifie tout ?". C'est un trou logique réel du v1 qui produit des faux positifs persistants.

**How to apply:**
- Phase 3 (API) : implémenter la dédup par type+date dans `verification.py` ou en pré-traitement.
- Phase 5 (n8n + SF admin) : créer le trigger Tech_Dossier_verifier__c = FALSE.
- À monitorer en Phase 6 : taux de ré-analyses moyen, coût IA / dossier. Si > 0,50 € moyenne, basculer Niveau 2 ou 3.
- Le coût supplémentaire de ré-analyse complète est acceptable au MVP — la fiabilité du verdict prime.
