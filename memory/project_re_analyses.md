---
name: project_re_analyses
description: Quand le vendeur redépose un dossier corrigé, l'ancien fichier reste dans SF et pollue l'analyse — solution en 3 niveaux (ADR-015)
metadata:
  type: project
---

Le vendeur ne crée jamais un nouveau dossier après anomalie : il modifie le dossier SF existant. Donc on écoute un **changement de statut SF** (pas la modification d'un fichier individuel).

**Décision (ADR-015 révisée 2026-05-13)** :

Cycle de vie SF d'un dossier (nouveau champ `Statut_dossier__c` sur Opportunity) :
- `nouveau` → vendeur vient d'uploader, jamais analysé
- `en_cours_analyse` → n8n a verrouillé
- `en_attente_validation_comptable` → API a fini, attend le dashboard
- `valide_conforme` → comptable a validé, FIN
- `en_anomalie_a_corriger` → comptable a rejeté, mail vendeur envoyé
- `corrige_a_reverifier` → vendeur a corrigé et cliqué "J'ai corrigé", retour analyse

Trigger SF : sur passage à `nouveau` ou `corrige_a_reverifier` → `Tech_Dossier_verifier__c = FALSE` → n8n picke.

L'API dédup côté Python : pour chaque type de document détecté, garde le `NEILON__File__c` le plus récent (`CreatedDate DESC`).

**Why:** L'utilisatrice (2026-05-13) a précisé que le vendeur ne crée jamais un nouveau dossier — il modifie le statut SF du dossier existant. Donc il faut écouter le statut SF, pas le fichier. Ça remplace l'approche initiale "trigger sur NEILON__File__c créé" qui était plus fragile.

**How to apply:**
- Phase 3 (API) : implémenter la dédup par type+date dans `verification.py` ou en pré-traitement.
- Phase 5 (n8n + SF admin) : créer le picklist `Statut_dossier__c` avec les 6 valeurs, le trigger sur changement, et le bouton "J'ai corrigé" côté vendeur SF.
- À monitorer en Phase 6 : taux de dossiers bloqués > 7 jours en `en_anomalie_a_corriger` (vendeur a oublié de cliquer), nb moyen de boucles par dossier, coût IA / dossier.
