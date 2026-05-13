# Glossaire métier — Leasing Social

> Vocabulaire et règles à connaître pour comprendre le projet. À consulter par Claude Code avant toute implémentation de règle métier.

## Acronymes et concepts

### Leasing Social
Aide d'État mise en place par le gouvernement français permettant à des ménages modestes de louer un véhicule électrique neuf pour environ 100-200 €/mois, grâce à une aide directe versée par l'État (jusqu'à 7000 €). Géré par l'ASP. Démarré 2024, prolongé/réformé 2025.

### ASP
**Agence de Services et de Paiement** — Organisme public français qui verse les aides au constructeur/loueur après vérification du dossier. C'est l'ASP qui contrôle la conformité. **Notre système doit anticiper leurs critères pour éviter les refus.**

### BDC
**Bon De Commande** — Document signé par le client et le concessionnaire au moment de la commande du véhicule. Contient : prix HT/TTC, modèle, options, date de livraison prévue, signatures. Pièce centrale du dossier.

### CGV / Contrat de location
Le document juridique qui formalise la location longue durée. Indique durée (mois), kilométrage annuel, montant du loyer mensuel, identité du loueur (souvent une filiale financière du constructeur).

### Concession
Point de vente HESS. Une concession appartient à une marque (ex: "Fiat Belfort", "Hyundai Strasbourg"). Le groupe HESS a ~55 concessions.

### RFR
**Revenu Fiscal de Référence** — Indicateur figurant sur l'avis d'imposition, utilisé pour évaluer l'éligibilité au Leasing Social. Calculé sur l'année N-2 (en 2026 on regarde l'avis 2024 sur revenus 2023, ou l'avis 2025 sur revenus 2024 selon les règles ASP en vigueur).

### Nombre de parts (fiscal)
Indicateur du quotient familial sur l'avis d'imposition. Sert au calcul `RFR / nb_parts` qui doit être ≤ 16 300 € pour être éligible.

### Géoportail
Service public en ligne de calcul d'itinéraire. **Pièce obligatoire** du dossier qui prouve la distance domicile-travail. Doit être généré en mode **"Plus court"** (et pas "Plus rapide"). Si distance < 15 km : obligatoire pour confirmer que le client n'est pas dans la zone de service public alternatif.

### Attestation gros rouleur
Document signé par le client (et idéalement employeur avec cachet) attestant qu'il fait un trajet domicile-travail régulier important. Avec adresses du client ET de l'employeur.

### Macaron "Avec l'État je roule plus vert"
Sticker apposé sur le véhicule (parfois pare-brise) attestant du dispositif. Photo recommandée mais pas toujours obligatoire selon les versions de la réglementation.

### VIN
**Vehicle Identification Number** — Numéro de série unique du véhicule, gravé sur le châssis. Photo obligatoire au dossier (VIN visible).

### NEILON__File__c
Objet custom Salesforce du groupe HESS qui représente un fichier attaché à une opportunité. Le champ `NEILON__File_Presigned_URL__c` contient une URL signée temporaire pour télécharger le fichier.

### Opportunity (Salesforce)
Entité Salesforce représentant une vente en cours. Champs clés pour nous :
- `Id` : identifiant unique
- `Name` : nom du dossier (ex: "OPP-2026-12345")
- `Leasing_electrique__c` : booléen, true si c'est un dossier Leasing Social
- `Tech_Dossier_verifier__c` : booléen, flag pour indiquer si on l'a déjà traité
- `Conformite_du_dossier__c` : statut (ex: "Document absent ou à corriger", "Conforme")
- `Concession_du_proprietaire__c` : nom de la concession (ex: "Fiat Belfort")
- `Date_livraison_definitive__c` : date de livraison (à mettre à jour depuis BDC)
- `Description` : champ texte libre

---

## Liste des documents attendus dans un dossier

### Obligatoires (ASP 2025)

1. **Justificatif d'identité** — CNI, passeport, titre de séjour ou pièce étrangère valide
2. **Permis de conduire** — Ancien format papier ou nouveau format carte
3. **Justificatif de domicile** — Moins de 3 mois, **jamais facture mobile**
4. **Avis d'imposition complet** — Année N-2, lisible
5. **Attestation gros rouleur** — Signée, datée, idéalement avec cachet employeur
6. **Attestation respect des engagements** — Document type signé par le client
7. **Attestation loyer < 200 €** — Mentionnant l'aide d'État déduite
8. **Bon de commande (BDC)** — Signé, avec prix HT et TTC, date livraison
9. **Contrat de location** — Signé, mentionnant l'aide
10. **Certificat d'immatriculation (carte grise)** — Une fois le véhicule immatriculé
11. **Photo VIN** — Numéro de série lisible
12. **Photo arrière véhicule** — Plaque visible + absence de pot d'échappement
13. **Géoportail** — Si distance < 15 km
14. **Fiche d'information restitution du véhicule**

### Facultatifs (selon contexte)

- Attestation rattachement foyer fiscal (si client rattaché)
- Facture d'achat (entre concessionnaire et loueur)
- Échéancier / quittance / plan de location (avec immat.)
- Photo macaron "Avec l'État je roule plus vert"
- Attestation URSSAF (si travailleur indépendant)

### Documents NON requis (correction PDF d'amélioration v2)

- **RIB** — n'est pas une pièce attendue par l'ASP, ne pas demander dans les prompts ni vérifier comme manquant.
- **Fiche de paie** — pas attendue dans le dossier.

> Le prompt vérificateur v1 (cf `N8N.txt` node "Vérificateur conformité") liste actuellement le RIB comme obligatoire. **Bug à corriger en Phase 2.**

---

## Règles ASP 2025 — référence (à coder dans `app/core/verification.py`)

### Règles éligibilité client

| Règle | Seuil / condition | Critère bloquant |
|-------|-------------------|------------------|
| RFR / parts | ≤ 16 300 € | Oui |
| Identité valide à date de livraison | Date expiration > date livraison | Oui |
| Permis valide à date de livraison | Nouveau format : date expiration > date livraison ; Ancien format : tolérance (pas de date d'expiration en général) | Oui |
| Justificatif domicile | ≤ 3 mois à date du 1er loyer | Oui |
| Justificatif domicile non-mobile | Pas une facture téléphone mobile | Oui |

### Règles véhicule / aide

| Règle | Seuil / condition | Critère bloquant |
|-------|-------------------|------------------|
| Aide ≤ 27 % du prix TTC | **Calculée sur prix TTC** du BDC (jamais HT — bug v1) | Oui |
| Aide ≤ 7000 € en absolu | Plafond fixe | Oui |
| Pas de mention "Bonus écologique" sur BDC | Mention interdite | Oui |
| Loyer mensuel < 200 € **hors options/prestations annexes** | Distinguer strictement "hors options" vs "avec options" sur le BDC et le contrat (bug v1 récurrent) | Oui |
| Durée location ≥ 36 mois (3 ans) | Sur contrat de location | Oui |
| Kilométrage ≥ 12 000 km/an | Sur contrat de location | Oui |
| Frais autorisés | Mise à la route, certificats, frais d'envoi, taxes, **immatriculation, pack livraison, frais de préparation** | Tout autre frais = bloquant |
| Date de début de dispositif | À partir du 30/09/2025 | Documents postérieurs OK |
| Délai BDC → livraison ≤ 6 mois | Date livraison ≤ date BDC + 6 mois | Alerte (à l'approche du délai) |

### Règles loyer / mensualités (PDF v2, à implémenter en Phase 3)

| Règle | Seuil / condition | Critère bloquant |
|-------|-------------------|------------------|
| Montant 1ère mensualité avant déduction aide | = montant de l'aide figurant sur BDC/contrat | Oui (écart = anomalie) |
| Montant 1ère mensualité après déduction aide | = 0 € | Oui (écart = anomalie) |
| Mensualités ultérieures moyennes | = loyer hors options/prestations annexes du contrat | Oui (écart = anomalie) |
| Mensualités ultérieures | ≤ 200 € | Oui |

### Règles distance / géoportail

| Règle | Seuil / condition | Critère bloquant |
|-------|-------------------|------------------|
| Mode de calcul Géoportail | Doit être "Plus court" | Oui (si "Plus rapide" → invalide) |
| Distance domicile-travail | Si < 15 km : géoportail obligatoire | Oui |
| Zone surveillance | 15.01 à 18 km : conforme avec alerte | Non bloquant |
| Distance excessive | > 100 km : alerte | Non bloquant (mais vérifier cohérence) |

### Règles photos

| Règle | Seuil / condition | Critère bloquant |
|-------|-------------------|------------------|
| Photo VIN | VIN lisible | Oui |
| Photo arrière | Plaque visible + pas de pot d'échappement | Oui |
| Photo macaron | Recommandée, pas bloquante | Non |

### Règles signatures

| Document | Signature requise |
|----------|-------------------|
| BDC | Client + concession |
| Contrat location | Client + loueur |
| Attestations | Client (+ employeur si gros rouleur) |
| Avis d'imposition | Lisible suffit, pas de signature |

---

## Valeurs de référence (à externaliser en config plus tard)

```python
# app/core/verification_rules.py (à créer en Phase 3)

RFR_PAR_PART_MAX = 16_300  # €
AIDE_RATIO_MAX = 0.27       # 27% du prix TTC
AIDE_PLAFOND = 7_000        # €
LOYER_MAX_HORS_OPTION = 200 # €/mois
DUREE_MIN_MOIS = 36
KM_MIN_PAR_AN = 12_000
DISTANCE_GEOPORTAIL_OBLIGATOIRE = 15  # km
JUSTIF_DOMICILE_MAX_MOIS = 3
DATE_DEBUT_DISPOSITIF = "2025-09-30"
DELAI_BDC_LIVRAISON_MAX_MOIS = 6
FRAIS_AUTORISES = [
    "mise à la route",
    "certificats",
    "frais d'envoi",
    "taxes",
    "immatriculation",
    "pack livraison",
    "frais de préparation",
]
MENTIONS_INTERDITES_BDC = ["Bonus écologique"]
JUSTIF_DOMICILE_INTERDITS = ["facture mobile", "facture téléphone mobile"]
GEOPORTAIL_MODE_REQUIS = "Plus court"
```

**Important** : ces valeurs peuvent évoluer si l'ASP modifie le dispositif. Il faut pouvoir les changer **sans redéployer**. Stratégie : les mettre dans une table `parametres_asp` en base Supabase, avec date d'effet. Le système prend la valeur en vigueur à la date du dossier.

---

## Marques à gérer

D'après le mapping concessions du workflow n8n v1 (`N8N.txt`, node "Mapping concession") :

| Marque | Nb concessions HESS approx |
|--------|----------------------------|
| Fiat | 6 |
| Jeep | 1 (mutualisé avec Fiat Dijon) |
| Hyundai | 7 |
| Nissan | 11 |
| Opel | 10 |
| Peugeot | 4 |
| Renault | 11 |
| Toyota | 11 |

Total côté n8n actuel : 8 marques, ~58 concessions.

**⚠️ Le périmètre HESS réel est de 10 à 15 marques** (info utilisatrice 2026-05-13). Les marques manquantes dans le mapping n8n (Citroën, Volkswagen, Dacia, Mazda, Suzuki… à confirmer) seront identifiées en Phase 1 à partir de la requête Salesforce sur `Concession_du_proprietaire__c` distinct, puis ajoutées au mapping Supabase.

**Décisions à valider en Phase 1** :
- Si Jeep et Fiat partagent le même BDC, mutualiser le prompt.
- Identifier les marques absentes du mapping v1 et leur volume (priorité de production des prompts).

---

## Cas limites métier à surveiller

- **Travailleur indépendant** : nécessite une attestation URSSAF en plus
- **Couple marié, mais commandé au nom d'un seul** : vérifier que le RFR du foyer est OK (l'avis d'imposition est commun)
- **Étudiant rattaché au foyer fiscal des parents** : attestation de rattachement nécessaire
- **Pièce d'identité étrangère** : titre de séjour obligatoire valide
- **Dossier livré avant 30/09/2025** : non éligible au dispositif (mais cas rare désormais)
- **Véhicule d'occasion** : ce dispositif ne couvre que le neuf
- **Concession = "Siège"** : dossier **invalide d'office**. Le Siège HESS n'est pas un point de vente, donc une opportunité Leasing rattachée au Siège est une erreur de saisie côté Salesforce. À exclure de l'extraction Phase 1 et à rejeter automatiquement en Phase 3 (`verification.py`).

---

## Sources réglementaires

- Décret 2024-XXX (Leasing Social initial)
- Décret de prolongation 2025
- Documentation ASP (à consolider en Phase 1)
- Spécifications fournies par Aurélien Pottier et Alexandre Schott (à formaliser)

**Important** : ce glossaire est la **référence interne** du projet. Si une règle évolue suite à une réforme ASP, mettre à jour ce fichier **avant** de toucher au code.
