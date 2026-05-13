---
name: feedback_workflow
description: Préférence utilisateur — avancer sans s'arrêter sur les clarifications, trancher et corriger ensuite
metadata:
  type: feedback
---

L'utilisatrice a explicitement demandé de travailler sans s'arrêter pour des questions de clarification. Quand un choix doit être fait, prendre la décision raisonnable et continuer ; elle redirige si nécessaire.

**Why:** Elle a posé l'instruction au début de la session ("work without stopping for clarifying questions").

**How to apply:** Sur ce projet, ne pas utiliser AskUserQuestion. Choisir l'option la plus sûre (verdict par défaut "non conforme" en cas de doute, scripts idempotents par défaut, etc.) et avancer. Ne pas demander confirmation avant d'écrire des fichiers de doc ou des scripts ; demander uniquement avant les actions destructrices ou les push externes (cf. CLAUDE.md).
