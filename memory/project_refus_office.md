---
name: project_refus_office
description: Règles de refus d'office — bypass IA + bypass comptable, mail vendeur direct (ADR-017)
metadata:
  type: project
---

Certains dossiers sont rejetés par une **règle binaire et incontestable**, sans passer par l'IA ni le comptable. Mail direct au vendeur, CC comptable pour audit, update SF immédiat.

**Décision (ADR-017)** :
- Module `app/core/refus_office.py` à créer en Phase 3
- Appelé **avant** l'appel Gemini dans `/analyze`
- Si match → verdict `refus_office`, court-circuit du pipeline
- Template mail dédié `mail_refus_office.html` (Phase 5)
- Workflow n8n `Leasing_v2_refus_office` (Phase 5)

**Règles actuelles (liste évolutive)** :
- `R001_siege` : `Concession_du_proprietaire__c == 'Siège'` → "rattacher à un point de vente"
- `R002_avant_dispositif` (à valider) : `CloseDate < 2025-09-30` → "dispositif pas en vigueur"

**Why:** L'utilisatrice (2026-05-13) a demandé d'éviter de gaspiller tokens IA + temps comptable sur des cas évidents comme "Siège" (cf [[project_siege_invalide]]).

**How to apply:**
- Liste **conservatrice** : ajouter une règle uniquement si elle est 100% binaire et incontestable.
- Distinct du flow standard (ADR-013 = validation comptable systématique). Refus d'office = 5e verdict (`refus_office`), exception explicite.
- Comptable en CC du mail (info uniquement, pas de validation à faire).
- Statut SF à passer directement à `en_anomalie_a_corriger` (skip `en_attente_validation_comptable`).
- Tests unitaires obligatoires sur chaque règle (cas positif + cas négatif), comme pour les autres règles ASP.
