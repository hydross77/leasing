---
name: project_ameliorations_v2
description: Axes d'amélioration produit demandés dans le PDF — nouvelles features à intégrer dans la roadmap v2
metadata:
  type: project
---

Nouvelles fonctionnalités demandées dans le PDF "Amélioration Leasing Social". À intégrer dans la roadmap (probablement Phase 3 / 5 selon la complexité).

1. **Relance automatique e-mail post-livraison** : pour les dossiers déjà validés "bon pour livraison" dans Salesforce, envoi automatique d'un mail demandant les documents à fournir après livraison (facture vente, carte grise, photo VIN, photo arrière avec immatriculation, version finale des attestations datées/signées avec lieu et immatriculation pour respect des loyers et engagements).

2. **Alerte délai 6 mois après signature BDC** : surveiller la date de signature du BDC ; envoi de mail à l'approche du délai des 6 mois (= délai max légal entre commande et livraison).

3. **Contrôle attestation respect des loyers** :
   - Montant 1ère mensualité avant déduction aide = montant de l'aide sur BDC/contrat
   - Montant 1ère mensualité après déduction aide = 0 € (alerte si différent)
   - Mensualités ultérieures = loyer hors options/prestations annexes du contrat
   - Alerte si mensualité > 200 € OU écart avec montant contractuel.

4. **Nouvelle catégorie Salesforce "livré"** : dissocier les véhicules effectivement livrés des "bon pour livraison" qui n'ont pas encore été livrés. Synchroniser la date de livraison réelle ICAR / Salesforce.

5. **Renommage IA des documents anonymes** : les pièces uploadées sous "Scan_20251001_092559" ou "scanner@groupehess.com_20260303_1" doivent être renommées par l'IA d'après leur type détecté (BDC, Pièce d'identité, Contrat, Attestation, etc.).

6. **Documents à retirer de la liste obligatoire** : RIB et fiche de paie ne sont **plus** nécessaires (cf. [[project_docs_non_requis]]).

**Why:** Ces points viennent directement des retours utilisateurs / concessions (PDF transmis le 2026-05-13).

**How to apply:**
- Points 1, 2, 4 → Phase 5 (intégration n8n) : ces relances sortent du périmètre de l'API d'analyse, elles relèvent de l'orchestrateur n8n + Salesforce.
- Points 3, 5 → Phase 2 (prompts) + Phase 3 (règles métier) : à inclure dans le prompt vérification et dans `verification.py`.
- Point 6 → mise à jour immédiate du glossaire pour ne pas générer de faux négatifs en Phase 1/2.
