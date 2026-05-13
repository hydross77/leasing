---
name: project_defense_profondeur
description: Défense en profondeur en 5 niveaux face aux changements de format documents marques (ADR-018)
metadata:
  type: project
---

Quand une marque change le format de ses documents (refonte BDC Fiat, nouveau contrat Stellantis, etc.), 5 niveaux de filet empilés garantissent qu'aucun dossier ne sort erroné.

**Les 5 niveaux** :
1. **Cascade prompts** (ADR-005) : `(marque, concession)` → `(marque, NULL)` → `('default', NULL)`
2. **Validation Pydantic stricte** (ADR-009) : retry 2x puis `erreur_technique`
3. **Indice de confiance auto-calculé** : les dossiers faibles remontent en haut du dashboard comptable
4. **Détection de drift** (Phase 6) : alerte Sentry si une marque chute brutalement
5. **Filet ultime — validation comptable systématique** (ADR-013) : aucun mail vendeur sans clic comptable

**Why:** L'utilisatrice (2026-05-13) a posé la question "imaginons qu'il change leur format, il y a un fallback ?". Important d'expliciter la résilience pour qu'elle soit confiante dans l'archi.

**How to apply:**
- Phase 3 : implémenter niveaux 1, 2, 3 dans l'API
- Phase 5 : implémenter niveau 5 (validation comptable obligatoire)
- Phase 6 : implémenter niveau 4 (monitoring drift, alertes Sentry)
- Stabilisateur naturel : ~8 docs sur 15 dans un dossier sont des Cerfa standardisés ASP qui ne bougent pas. Seul BDC + contrat varient par marque.
