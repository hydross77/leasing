# Améliorations v2 — Consolidation des retours du PDF "Amélioration Leasing Social"

> Document source : `Amélioration Leasing Social.pdf` (3 pages, transmis par le manager le 2026-05-13).
> Objectif : centraliser les anomalies à corriger (faux positifs / faux négatifs du système v1) et les nouvelles fonctionnalités demandées, avec rattachement aux phases de la roadmap.

---

## 1. Anomalies du système v1 à corriger

Le système actuel (workflow n8n + prompt Gemini + prompt GPT-5-mini, cf [`N8N.txt`](N8N.txt)) produit des **faux positifs** identifiés en production. Liste à utiliser comme **test set de non-régression** en Phase 4.

| # | Catégorie | Symptôme observé | Cas | Cible Phase |
|---|-----------|------------------|-----|-------------|
| A1 | Avis d'imposition — RFR/parts | Alerte "non conforme" alors que `RFR/parts ≤ 16 300 €` | Renault Mulhouse / Zakaria MAJDOUNE (18 624 € / 2 parts = 9 312 €) | 2 (prompt) + 3 (vérif) |
| A2 | Pièce d'identité — date | "Absence de date de délivrance/expiration" alors qu'elle figure sur la CNI | Renault Saverne / MEHMET SEN | 2 (prompt extraction) |
| A3 | Pièce d'identité — détection | "Absence de pièce d'identité conforme" alors qu'elle est présente | Plusieurs cas | 2 (prompt) — robustesse OCR sur scans |
| A4 | BDC — prix TTC | "Prix TTC manquant" alors qu'il figure sur le BDC | Hyundai Strasbourg / SCHUBNEL | 2 (prompt par marque) |
| A5 | BDC — calcul aide | Aide calculée sur **HT** au lieu du **TTC** → seuil 27 % faussé | Renault Illkirch / MOUNIR BOUKKAZA (aide 7000 € vs seuil 27 % HT 6323,96 €) | 3 (`verification.py` — règle dure : aide vs TTC, jamais HT) |
| A6 | Frais sur BDC | Confusion frais administratifs (interdits) vs frais d'immatriculation / pack livraison / mise à la route / préparation (autorisés) | Renault Colmar / Stéphane Siettler (313,76 € de frais "admin" qui étaient en fait immat) ; Peugeot Reims / FELLAH (pack livraison autorisé) | 2 (prompt typer les frais) + 3 (liste blanche `FRAIS_AUTORISES`) |
| A7 | Justificatif de domicile — date | "Daté du futur" sur un document conforme | Renault Sélestat / JM Hein | 2 (prompt — extraction date robuste) |
| A8 | BDC — délai 6 mois + cohérence dates | "Délai livraison > 6 mois et contradiction de dates" alors que BDC 30/09/2025 + livraison déc. 2025 cohérents | Renault Mulhouse / Camille GAULT | 3 (`verification.py` — calcul délai = `date_livraison - date_bdc`, max 6 mois) |
| A9 | BDC — case cochée location/achat | "Achat comptant détecté" alors que la case "location" est cochée | Hyundai Strasbourg / Mustafa UCA ; Peugeot Reims / DE GUILLEBON | 2 (prompt par marque — focus sur les cases à cocher, retour explicite `nature_bdc: "location"`) |
| A10 | Contrat — loyer hors options vs avec options | IA prend le loyer **avec** options (> 200 €) au lieu du loyer **hors** options (< 200 €) | Fiat Mulhouse / Mohamed RIAD (268,14 € vs 196,96 €) | 2 (prompt — extraction `loyer_hors_option` ET `loyer_avec_option` séparément) + 3 (vérif sur le hors_option uniquement) |

### Documents retirés de la liste obligatoire

D'après page 3 du PDF :

- **RIB** : retiré (le prompt vérificateur v1 le liste à tort dans les obligatoires)
- **Fiche de paie** : retirée

Mise à jour effectuée dans [`glossaire.md`](glossaire.md).

---

## 2. Nouvelles fonctionnalités demandées

### 2.1 Relances automatiques post-livraison (Phase 5 — n8n)

Pour les dossiers en statut **"bon pour livraison"** dans Salesforce, envoi automatique d'un e-mail demandant les documents à fournir après livraison :

- Facture de vente
- Carte grise (certificat d'immatriculation définitif)
- Photo du véhicule (VIN visible)
- Photo arrière du véhicule (avec immatriculation)
- Version finale des attestations : datées, signées, avec lieu et immatriculation
  - Attestation respect des loyers
  - Attestation respect des engagements

**Périmètre technique** : ce flux relève de l'**orchestrateur n8n** (et non de l'API d'analyse). Workflow `Leasing_v2_relances` à créer en Phase 5.

### 2.2 Alerte délai 6 mois après signature BDC (Phase 5 — n8n)

Surveillance des BDC signés ≥ 5 mois sans livraison. Envoi d'un mail d'alerte à la concession (et à Renzo en CC) pour relance avant péremption du dispositif.

Côté API : exposer un endpoint `GET /dossiers/alerte-6-mois` ou alimenter directement via un champ SF que n8n surveille.

### 2.3 Contrôle attestation respect des loyers renforcé (Phase 3 — `verification.py`)

Quatre nouveaux contrôles à coder dans la couche métier :

| Contrôle | Règle | Action si écart |
|----------|-------|-----------------|
| Montant 1ère mensualité avant déduction aide | = montant de l'aide indiquée sur BDC/contrat | Anomalie bloquante |
| Montant 1ère mensualité après déduction aide | = 0 € | Anomalie bloquante |
| Mensualités ultérieures moyennes | = loyer hors options/prestations annexes du contrat | Anomalie bloquante |
| Mensualités ultérieures | ≤ 200 € (et écart nul avec le contrat) | Anomalie bloquante |

Test unitaire dédié par règle.

### 2.4 Nouvelle catégorie Salesforce "livré" (Phase 5/6)

Aujourd'hui un dossier passe `bon pour livraison` → directement à validation finale. Ajouter un statut intermédiaire **"livré"** pour distinguer :
- `bon pour livraison` : validé mais véhicule pas encore livré
- `livré` : véhicule livré, on attend les documents post-livraison
- `validé` : tout est OK

Cela permet de **déclencher les relances post-livraison (2.1)** uniquement sur le statut `livré`.

**Synchronisation** : pousser la date de livraison réelle depuis ICAR (compte client) vers le champ `Date_livraison_definitive__c` de l'opportunité SF. **Non couvert par l'API**, c'est un sujet n8n + SF custom field.

### 2.5 Renommage IA des pièces anonymes (Phase 3 — endpoint dédié)

Les pièces uploadées avec un nom générique (ex. `Scan_20251001_092559`, `scanner@groupehess.com_20260303_1`) doivent être renommées par l'API d'après leur type détecté :

- `BDC.pdf`
- `Pièce d'identité.pdf`
- `Contrat de location.pdf`
- `Attestation gros rouleur.pdf`
- etc.

**Implémentation** :
- L'API détecte le type via Gemini (déjà fait dans `donnees_extraites.type_document`).
- L'API renvoie dans sa réponse `/analyze` un mapping `{ file_id: nom_propose }`.
- n8n appelle Salesforce pour patcher le champ `Name` du `NEILON__File__c`.

---

## 3. Rattachement à la roadmap

| Item | Phase cible |
|------|-------------|
| A1–A10 (anomalies) | Phase 2 (prompts) + Phase 3 (règles métier) — test set Phase 4 |
| Documents RIB / fiche paie retirés | Phase 2 (prompts) — déjà acté dans le glossaire |
| 2.1 Relances post-livraison | Phase 5 (n8n) |
| 2.2 Alerte délai 6 mois | Phase 5 (n8n) — Phase 3 si endpoint API requis |
| 2.3 Contrôles loyers renforcés | Phase 3 (`verification.py`) — tests unitaires |
| 2.4 Statut "livré" | Phase 5/6 — coordination n8n + SF (hors API) |
| 2.5 Renommage pièces | Phase 3 (API renvoie le mapping) + Phase 5 (n8n patche SF) |

---

## 4. Cas test à intégrer au backtest (Phase 4)

Pour chaque cas listé en section 1, créer un dossier de test dans `tests/fixtures/backtest_anomalies_v1/` avec :
- Les PDFs anonymisés (ou metadonnées simulées si on ne peut pas dupliquer la donnée client)
- Le verdict attendu = **conforme**
- Une assertion explicite : le verdict v2 ne doit pas régresser sur cet écart précis.

Ces cas servent de **non-régression** : si on perd un de ces cas, on bloque le déploiement.
