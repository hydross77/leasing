---
name: feedback_etude_avant_code
description: Pour les prompts par marque/concession, étudier d'abord l'historique Salesforce des dossiers gagnés avant d'écrire le moindre prompt de production
metadata:
  type: feedback
---

Sur ce projet, **ne pas écrire de prompt par marque/concession en aveugle**. L'historique Salesforce des dossiers `Closed Won` + `Leasing_electrique__c = TRUE` contient déjà tous les formats de BDC, contrats et pièces qu'on rencontrera en production. C'est la source de vérité empirique pour la rétro-ingénierie.

**Why:** L'utilisatrice a explicitement rappelé (2026-05-13) que les prompts doivent être construits **après** étude du dataset, pas avant. Sinon on reproduit les faux positifs du système v1 (cf [[project_anomalies_v1]]).

**How to apply:**
- Phase 1 doit **terminer** avant Phase 2 — pas de raccourci.
- Le script `extract_won_dossiers.py` extrait + classe les dossiers par couple `(marque, concession)`.
- Le script `analyze_dataset.py` fait un premier passage Gemini avec un prompt **très ouvert** ("décris ce document") pour catalogue qualitatif.
- L'humain (Renzo + Aurélien + Alexandre) examine ensuite ~20 dossiers test par marque pour repérer les libellés, sections et mentions spécifiques.
- **Seulement après** cette étude, écriture des prompts par marque/concession en Phase 2.
- Aucune anticipation de prompts spécifiques dans le code livré en Phase 1.
