---
name: project_dashboard_pdf_preview
description: Le dashboard comptable doit permettre à Axel de prévisualiser les PDFs des dossiers directement (Phase 5b)
metadata:
  type: project
---

Axel doit pouvoir **prévisualiser les PDFs** directement depuis le dashboard pour valider rapidement chaque verdict (sans changer d'onglet vers Salesforce).

**Décision (2026-05-13)** : implémenter en **Niveau 2** au MVP Phase 5b :
- Endpoint API `GET /dossiers/{opp_id}/fichiers/{file_id}` qui stream le PDF depuis SF (presigned URL gérée en backend)
- Composant Streamlit `streamlit-pdf-viewer` ou simple `<iframe>` qui ouvre le PDF en overlay au clic sur un fichier

**Why:** L'utilisatrice (2026-05-13) a posé la question — c'est ergonomiquement nécessaire pour qu'Axel valide 100 dossiers/jour sans switcher constamment d'outil.

**How to apply:**
- Phase 3 : ajouter l'endpoint API stream du PDF (~30 min)
- Phase 5b : composant viewer côté Streamlit (~20 min)
- RGPD : auth Axel obligatoire, pas de cache navigateur, pas de log du contenu PDF
- Si les PDFs sont trop lourds (10-15 MB), passer en Niveau 3 (pré-rendu pages en PNG)
- Post-MVP : Niveau 4 (annotations contextuelles avec surlignage de la zone problématique par anomalie) — nécessite que Gemini renvoie `page_number` + `bbox` dans l'extraction.
