# Formats des dossiers par marque/concession

> Synthèse rétro-ingénierie issue de l'analyse exploratoire Gemini 2.5 Pro (Phase 1).
> Sert de **matériau d'entrée à la Phase 2** (écriture des prompts).
>
> Source : `dataset/exploration_qualitative.jsonl` (analyse à prompt ouvert sur dossiers gagnés HESS sur 12 mois).
> À enrichir au fur et à mesure que les analyses des autres marques se terminent.

---

## Vue d'ensemble dataset (extraction Phase 1)

- **296 dossiers gagnés** sur 12 mois — répartition : Renault 56%, Fiat 21%, Peugeot 12%, Hyundai 6%, Opel 5%
- **5 marques actives** sur le Leasing Social HESS (Toyota / Nissan / Jeep du mapping n8n v1 absents — pas de volume)
- **Top 5 couples (marque, concession)** à prioriser : Renault Strasbourg Illkirch (38), Renault Mulhouse (30), Renault Strasbourg Hautepierre (27), Fiat Bischheim (26), Fiat Mulhouse (25)

---

## FIAT

### Couverture analyse
- **6 concessions analysées** : Belfort, Besançon, Bischheim, Colmar, Dijon, Mulhouse
- **223 fichiers analysés** par Gemini 2.5 Pro (taux succès JSON ≈ 95%)
- 62 dossiers Fiat dans le dataset total

### Logos & en-têtes détectés

| Logo | Présence | Contexte |
|------|----------|----------|
| **FIAT** | Dominant | BDC, parfois sur attestations |
| **Alfa Romeo** | Fiat Besançon | Même groupe Stellantis, BDC partagé |
| **AUTO PRESTIGE (FIAT LANCIA ALFA ROMEO JEEP)** | Fiat Belfort | Cachet concession multi-marques Stellantis |
| **STELLANTIS FINANCE & SERVICES** | Sur **contrats de location** | Filiale financière, jamais sur BDC |
| **CREDIPAR** | Sur **carte grise** | Organisme de crédit propriétaire du véhicule pendant la LLD |
| **HESS AUTOMOBILE** | Cachet sur attestations | Identifie la concession |
| **RÉPUBLIQUE FRANÇAISE / ADEME / ASP / CEE** | Formulaires Cerfa officiels | Attestations leasing social |

### Bon de Commande (BDC) — format Fiat

**Libellés clés stables** :
- Prix HT : `Prix HT en €`
- Prix TTC : `Prix TTC en €`
- Variante Bischheim : `Prix Public conseillé:`
- Variante avec frais inclus : `Prix clés en mains (2)`

**Section "Achat" (cases à cocher — IMPORTANT pour nature)** :

⚠️ **Piège** : la section s'appelle "**Achat**" sur le BDC Fiat mais elle contient les options de **location** aussi. À ne PAS interpréter comme "achat comptant" par défaut.

Options présentes dans cette section :
- Comptant
- Crédit
- LOA
- **LLD** ← coché pour leasing social
- Autres (parfois "Autres Leasing électrique" coché chez Fiat Besançon)
- Variante "HE - LEASING ELECTRIQUE" (codification interne Besançon)

**Aides et remises sur BDC Fiat** (libellés à savoir reconnaître) :
- `Aides Gouvernementales - Leasing électrique` : -7 000 €
- `REMISE COMMUNE LEASING ELECTRIQUE` : -3 700 €
- `Remise commerciale leasing électrique 2025` : -6 000 €
- `REMISE LEASING SOCIAL` : -5 350 €
- `Aides Gouvernementales` : -7.000,00 €

**Frais détectés sur BDC Fiat** (souvent autorisés) :
- Carte Grise
- Carte Grise Grand Est 4CV
- Frais de mise à la route
- Frais de transport (parfois inclus dans "Prix clés en mains")
- Jeu de tapis
- Kit sécurité (gilet + triangle + extincteur)
- Traitement Carrosserie WAXOYL
- Marquage
- Autres prestations

⚠️ **Important** : sur le BDC Fiat, **le loyer mensuel, la durée et le kilométrage ne sont GÉNÉRALEMENT PAS présents**. Ces infos sont sur le contrat de location (Stellantis Finance) ou une simulation financière annexe. **Le prompt extraction_bdc_fiat doit autoriser ces champs à `null`** et ne pas les déclarer manquants.

### Contrat de location — format Fiat

- **Émetteur** : `STELLANTIS FINANCE & SERVICES` (pas Fiat directement)
- **Nature** : `CONTRAT DE LOCATION (VP/VU A USAGE PRIVE)` + mention `LEASING SOCIAL DE VÉHICULES ÉLECTRIQUES`
- **Libellé loyer** : `Loyers hors options et hors prestations facultatives`
- **Mention CEE** : `Programme CEE de location sociale de véhicules électriques`

### Attestation respect loyers — Fiat

- **Logo** : République Française / ADEME / CEE / ASP
- **Libellé montant** : `Mensualités ultérieures moyennes`
- **Formulaire Cerfa** : `LVEREB-1085` (formulaire officiel État)
- Mention récurrente : `Aide au leasing social d'un montant de 7000 €, intégralement déduite du montant du 1er loyer`

### Attestation respect engagements — Fiat

Liste des engagements à cocher (formulaire officiel, présent dans tous les dossiers) :

1. Être informé(e) du bénéfice de l'aide leasing social
2. Aucune caution exigée lors de la commande
3. Pas de cumul avec "prime coup de pouce TRA-EQ-117"
4. Pas de cumul avec bonus écologique (art. D.251-1)
5. Pas de cumul avec leasing 2024 (art. D.251-3)
6. Pas de sous-location
7. Pas de résiliation avant 3 ans
8. Réponse aux contrôles administratifs / visuels
9. Restitution de l'aide en cas d'anomalie détectée
10. Déclaration spontanée du non-respect
11. Réponse aux enquêtes ADEME
12. Consentement utilisation données (offres recharge)

→ Le prompt Phase 2 peut vérifier que ces 12 cases sont bien cochées sur l'attestation.

### Particularités Fiat à coder (pistes pour Phase 2 + Phase 3)

| # | Particularité | Type vérification | Phase |
|---|----------------|-------------------|-------|
| 1 | Aide État 7000 € annule **complètement** le 1er loyer | Vérif : `loyer_1 - aide = 0` | 3 (verification.py) |
| 2 | "REMISE GAMME LEASING ELECTRIQUE" sur facture | Indicateur conformité, pas anomalie | 2 (prompt) |
| 3 | Carte grise au nom de **CREDIPAR** | Normal pour LLD, ne pas alerter | 3 |
| 4 | Formulaire Cerfa LVEREB-1085 | Doit être présent, signé, daté | 3 |
| 5 | Mention non-cumul (bonus écolo, prime coup de pouce) | Doit être cochée | 3 |
| 6 | Multi-doc fréquent : plusieurs attestations dans un seul PDF | Prompt Gemini doit accepter des "documents composés" | 2 |

### Anomalies récurrentes détectées par Gemini sur Fiat

| Anomalie | Exemple | Faut-il alerter ? |
|----------|---------|--------------------|
| **Dates de signature dans le futur** (ex: 03/10/2025, 03/02/2025) | Probable erreur saisie OU date de livraison prévue | **À investiguer cas par cas** — pas systématiquement une anomalie |
| **Divergence orthographe nom client** entre 2 pages (ex: DANSORTIN vs DANJOUTIN) | Erreur de saisie | **Alerter** si la divergence est nominative significative |
| Pagination 13/36, 14/36, 24/36 | Dossier extrait d'un PDF plus volumineux | Pas une anomalie, juste informatif |

### Pistes pour le prompt `extraction_bdc_fiat` (Phase 2)

Briefing à donner à Gemini :
1. Le BDC Fiat appartient au groupe Stellantis (logos FIAT, Alfa Romeo, AUTO PRESTIGE possibles)
2. La section "**Achat**" contient les options de **location** (LOA, LLD, "Autres Leasing électrique") — ne pas interpréter comme "achat comptant" par défaut
3. Extraire séparément `prix_ttc` et `prix_clés_en_main` quand ils existent
4. Loyer/durée/km **probablement absents** du BDC — ne pas marquer comme manquant
5. Lister TOUS les frais avec leur libellé exact (Carte Grise, KIT SECURITE, etc.)
6. Lister TOUTES les aides/remises avec montant signé (-7000 €, -3700 €, etc.)
7. Retourner `nature_bdc: "location" | "achat" | null` d'après la case cochée

### Pistes pour le prompt `extraction_contrat_fiat`

- Logo `STELLANTIS FINANCE & SERVICES` attendu en en-tête
- Extraire spécifiquement le libellé `Loyers hors options et hors prestations facultatives` (= valeur à comparer aux 200 €)
- Distinguer `loyer_avec_options` vs `loyer_hors_options` (bug v1 récurrent)
- Durée en mois, kilométrage annuel

---

## RENAULT — _en attente d'analyse_

> ⏳ **Pas encore de données concrètes**. L'analyse exploratoire toutes marques tourne en background, cette section sera rédigée **uniquement à partir du JSONL Gemini** quand le job sera terminé.

À analyser (issu de `dataset-stats.md`, factuel) :
- Renault Strasbourg Illkirch : 38 dossiers
- Renault Mulhouse : 30
- Renault Strasbourg Hautepierre : 27
- Renault Colmar : 18
- Renault Montbéliard : 15
- Renault Sélestat : 13
- Renault Haguenau : 11
- Renault Saint-Louis : 9
- Renault Saverne : 5
- Renault Belfort : 1
- Total : **167 dossiers Renault** (56% du dataset — marque prioritaire)

---

## PEUGEOT — _en attente d'analyse_

> ⏳ **Pas encore de données concrètes**.

À analyser (factuel) :
- Peugeot Reims : 18
- Peugeot Charleville : 15
- Peugeot Sedan : 3
- Total : **36 dossiers Peugeot**

---

## HYUNDAI — _en attente d'analyse_

> ⏳ **Pas encore de données concrètes**.

À analyser (factuel) :
- Hyundai Reims : 5
- Hyundai Strasbourg : 5
- Hyundai Epernay : 3
- Hyundai Mulhouse : 2
- Hyundai Chalons : 1 ⚠️ **hors mapping n8n v1** — à normaliser vers "Hyundai Châlons" (avec accent)
- Hyundai Colmar : 1
- Total : **17 dossiers Hyundai**

---

## OPEL — _en attente d'analyse_

> ⏳ **Pas encore de données concrètes**.

À analyser (factuel) :
- Opel Besançon : 6
- Opel Belfort : 3
- Opel Verdun : 2
- Opel Dijon : 1
- Opel Metz : 1
- Opel Nancy : 1
- Total : **14 dossiers Opel**

---

## Documents transversaux (toutes marques)

Ces documents sont **standardisés au niveau ASP/État**, donc identiques peu importe la marque :

| Document | Libellé / particularité |
|----------|-------------------------|
| Attestation respect engagements | Formulaire Cerfa **LVEREB-1085** — RÉPUBLIQUE FRANÇAISE / ADEME / ASP / CEE |
| Attestation respect loyers | Mention `Aide au leasing social d'un montant de 7000 €, intégralement déduite du montant du 1er loyer` |
| Avis d'imposition | Format standard DGFIP — RFR et nb_parts en tête |
| Géoportail | Capture web — mode `Plus court` requis (jamais `Plus rapide`) |
| Permis de conduire | Ancien format papier OU nouveau format carte |
| CNI | CNI nouvelle ou ancienne, ou passeport, ou titre de séjour |
| Justificatif domicile | EDF, eau, gaz, quittance loyer, avis taxe — **JAMAIS facture mobile** |
| Carte grise | Au nom du **loueur** (CREDIPAR, RCI, Hyundai Capital, etc.) — pas du client |

→ **Un seul prompt `extraction_pieces_admin`** suffit pour toutes ces pièces, peu importe la marque.

---

## Décisions Phase 2 issues de cette synthèse

1. **Prompt par marque obligatoire** sur BDC et contrat (formats vraiment différents : Stellantis vs Renault vs Hyundai)
2. **Prompt unique `extraction_pieces_admin`** sur les pièces ASP standardisées
3. **Surcharges concession à prévoir** :
   - Fiat Belfort (cachet "AUTO PRESTIGE" différent)
   - Fiat Besançon (logo Alfa Romeo apparaît sur BDC)
   - Autres à identifier quand l'analyse multi-marques sera terminée
4. **Pas de prompt pour Toyota / Nissan / Jeep** tant qu'on n'a pas de volume Leasing
5. **Inclure dans tous les prompts BDC** une instruction explicite sur :
   - Distinguer loyer hors options / avec options
   - Reconnaître la section "Achat" qui contient des options de location (Fiat)
   - Lister tous les frais avec libellé exact (typage autorisé/interdit fait en aval)
   - Retourner `nature_bdc: location/achat/null`
6. **Inclure dans tous les prompts contrat** :
   - Identifier la filiale financière (Stellantis Finance / RCI / Hyundai Capital)
   - Extraire séparément les 2 loyers (hors options ET avec options)
7. **Règles métier nouvelles** (Phase 3 — verification.py) :
   - 1er loyer après aide = 0 € (ADR PDF v2 §2.3 — déjà acté)
   - Détecter divergence orthographe nom client entre pages
   - Date signature future = à signaler mais pas bloquant
