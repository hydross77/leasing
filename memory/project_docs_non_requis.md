---
name: project_docs_non_requis
description: Documents retirés de la liste obligatoire — correction du glossaire suite au PDF d'amélioration
metadata:
  type: project
---

D'après le PDF "Amélioration Leasing Social" (page 3), les documents suivants ne sont **pas** nécessaires dans le dossier Leasing Social, malgré ce qu'indiquait initialement le glossaire :

- **RIB** : retiré (apparaissait comme obligatoire dans glossaire.md point 11)
- **Fiche de paie** : retirée (n'était pas dans le glossaire de toute façon — confirmer qu'on ne la demande pas)

**Why:** L'ASP 2025 ne réclame pas ces pièces ; les demander génère des faux négatifs ("document manquant") sur des dossiers conformes.

**How to apply:**
- Mettre à jour `glossaire.md` : retirer "RIB" du point 11 de la liste obligatoire ASP 2025.
- En Phase 2 (prompts) : ne pas demander à l'IA de chercher un RIB.
- En Phase 3 (`verification.py`) : la règle "RIB présent" ne doit pas figurer parmi les documents obligatoires.
- À reconfirmer côté métier (Aurélien Pottier / Alexandre Schott) avant le go en prod si doute, le RIB peut être utile à la concession mais n'est pas attendu par l'ASP.
