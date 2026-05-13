---
name: project_champs_sf
description: Champs SF existants utilisés par v2 (pas de nouveau champ à créer)
metadata:
  type: project
---

**Découverte 2026-05-13** : tous les champs SF nécessaires pour piloter v2 **existent déjà** sur l'Opportunity. ADR-015 doit être révisée pour ne PAS créer de nouveau champ `Statut_dossier__c`.

### Les 2 champs SF qu'on pilote

1. **`Tech_Dossier_verifier__c`** (booléen, existant)
   - Signal "à analyser" pour n8n
   - **Se décoche AUTOMATIQUEMENT** par SF dès qu'un fichier est modifié sur l'opportunité (mécanisme natif)
   - Notre API le repasse à TRUE après écriture du verdict en base + validation comptable

2. **`Conformite_du_dossier__c`** (picklist, existant)
   - Statut final ASP — **distinct de `StageName`** (qui est le cycle commercial)
   - Valeurs : `- Aucun -` / `Client inéligible` / `Document absent ou à corriger` / `Bon pour livraison` / `Dossier conforme après la livraison`

### Mapping verdict interne → valeur SF

| Notre `Verdict.statut` | `Conformite_du_dossier__c` |
|------------------------|----------------------------|
| `refus_office` (Siège, etc.) | `Client inéligible` |
| `non_conforme` (anomalies / docs manquants) | `Document absent ou à corriger` |
| `conforme` | `Bon pour livraison` |
| `erreur_technique` | Laisser tel quel (re-tente prochain cycle) |
| `aucun_doc` | Laisser tel quel + alerte interne |

### SOQL de production (Phase 5)

```sql
WHERE Leasing_electrique__c = TRUE
  AND Tech_Dossier_verifier__c = FALSE
  AND StageName = '4- Gagné'
  AND Conformite_du_dossier__c NOT IN (
    'Bon pour livraison',
    'Dossier conforme après la livraison',
    'Client inéligible'
  )
  AND Concession_du_proprietaire__c != 'Siège'
```

### Qui pilote quel champ (corrigé 2026-05-13)

| Champ | Système v2 | Comptable Axel | Vendeur |
|-------|------------|----------------|---------|
| `StageName` | **LECTURE seule** | Pilote sur SF | rien |
| `Conformite_du_dossier__c` | Écrit après validation | Peut override sur SF | rien |
| `Tech_Dossier_verifier__c` | Repasse TRUE après validation | Peut décocher pour ré-analyse | Décoché AUTO par SF à modif fichier |

⚠️ **Le système v2 ne touche JAMAIS à `StageName`** — c'est le comptable qui le pilote manuellement (1-Nouveau → 4-Gagné → 5-Perdu).

`StageName = '5- Perdu'` peut être mis par le comptable pour différentes raisons (abandon client, échec conformité, etc.). On ne fait pas l'amalgame avec `Conformite_du_dossier__c = 'Client inéligible'` qui est juste notre verdict ASP.

**Why:** L'utilisatrice (2026-05-13) a montré les valeurs réelles via captures SF et expliqué que `Tech_Dossier_verifier__c` se décoche automatiquement. Économie : 0 trigger SF custom + 0 nouveau champ à demander à l'admin.

**How to apply:**
- Phase 5 (intégration n8n) : utiliser cette SOQL telle quelle, pas de demande SF admin nécessaire
- Phase 3 (API) : écrire les bonnes valeurs picklist quand on patche SF (cf mapping ci-dessus)
- ADR-015 doit être révisée pour retirer la création de `Statut_dossier__c` et le bouton "J'ai corrigé".
