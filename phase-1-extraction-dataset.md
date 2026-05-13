# Phase 1 — Extraction et étude du dataset des dossiers gagnés

> **Pré-requis** : Phase 0 terminée (FastAPI healthcheck OK, Supabase provisionné, concessions seedées).
> **Principe directeur** : étude AVANT code de prompts. Aucun prompt de production n'est écrit en Phase 1.
> **Référence** : roadmap.md section "Phase 1", ADR-004 (exception stockage temporaire chiffré), `feedback_etude_avant_code` (memory).

---

## Objectif

Récupérer **tous les dossiers Leasing Social validés ("gagnés")** sur les 12 derniers mois depuis Salesforce, les organiser par couple `(marque, concession)`, et produire une cartographie qualitative des formats de pièces (BDC, contrat, attestations) qui servira à la rétro-ingénierie des prompts en Phase 2.

## Livrables

1. **`scripts/extract_won_dossiers.py`** — extraction Salesforce + téléchargement chiffré local
2. **`dataset/metadata.jsonl`** — métadonnées des dossiers (1 ligne par dossier)
3. **`dataset-stats.md`** — synthèse quantitative (nb dossiers/marque, nb pièces, marques inconnues)
4. **`scripts/analyze_dataset.py`** — passage Gemini exploratoire (prompt très ouvert)
5. **`dataset/exploration_qualitative.jsonl`** — 1 ligne par PDF analysé
6. **`dossier-formats-par-marque.md`** — synthèse humaine, base de la Phase 2

## Étape 1 — `scripts/extract_won_dossiers.py`

### Comportement attendu

```bash
# Extraction complète (12 mois glissants)
python scripts/extract_won_dossiers.py

# Limiter pour test
python scripts/extract_won_dossiers.py --limit 20

# Reprendre un run interrompu (idempotent)
python scripts/extract_won_dossiers.py --resume

# Sans téléchargement des PDFs (uniquement métadonnées)
python scripts/extract_won_dossiers.py --metadata-only

# Filtrer une marque
python scripts/extract_won_dossiers.py --marque renault
```

### SOQL

```sql
SELECT
    Id,
    Name,
    StageName,
    CloseDate,
    LastModifiedDate,
    Concession_du_proprietaire__c,
    Leasing_electrique__c,
    Conformite_du_dossier__c,
    Description
FROM Opportunity
WHERE
    Leasing_electrique__c = TRUE
    AND StageName = 'Closed Won'
    AND CloseDate >= LAST_N_MONTHS:12
ORDER BY CloseDate DESC
```

Puis pour chaque opportunité, une seconde requête :

```sql
SELECT
    Id,
    Name,
    CreatedDate,
    NEILON__Opportunity__c,
    NEILON__File_Presigned_URL__c
FROM NEILON__File__c
WHERE NEILON__Opportunity__c = '{opp_id}'
ORDER BY CreatedDate DESC
```

### Arborescence locale produite

```
dataset/
├── metadata.jsonl                              # 1 ligne par dossier
├── stats.json                                  # quantités agrégées
└── dossiers/
    ├── fiat/
    │   ├── Fiat Belfort/
    │   │   ├── 0061x000ABC123XYZ/
    │   │   │   ├── manifest.json               # opp metadata + files list
    │   │   │   ├── BDC_signe.pdf.enc           # chiffré Fernet
    │   │   │   ├── Scan_20251001_092559.pdf.enc
    │   │   │   └── ...
    │   │   └── 0061x000DEF456UVW/
    │   └── Fiat Mulhouse/
    ├── renault/
    └── ...
```

### Chiffrement local (ADR-004 exception)

- Clé Fernet dans `.env` (`DATASET_ENCRYPTION_KEY`)
- Chaque PDF téléchargé est chiffré **avant** écriture sur disque (jamais en clair sur le disque)
- Pour analyser, le script déchiffre en RAM puis envoie à Gemini

### Format `manifest.json` par opportunité

```json
{
  "opportunity_id": "0061x000ABC123XYZ",
  "opportunity_name": "OPP-2026-12345",
  "marque": "fiat",
  "concession": "Fiat Belfort",
  "close_date": "2025-12-15",
  "leasing_electrique": true,
  "files": [
    {
      "id": "a0X1x000000abc",
      "original_name": "BDC_signe.pdf",
      "size_bytes": 854321,
      "encrypted_path": "BDC_signe.pdf.enc",
      "downloaded_at": "2026-05-13T14:32:01Z"
    }
  ]
}
```

### Format `metadata.jsonl` (agrégat)

Une ligne JSON par dossier, identique au `manifest.json` ci-dessus mais aplaties. Sert aux stats et au `analyze_dataset.py`.

### Gestion d'erreurs

- Quota SF dépassé → backoff exponentiel + retry, sauvegarde du curseur (CloseDate) pour reprendre
- URL presigned expirée → retry en re-fetchant le `NEILON__File__c`
- Doublons (fichier déjà téléchargé) → skip silencieux (idempotence)

## Étape 2 — `dataset-stats.md`

Généré automatiquement à la fin de `extract_won_dossiers.py` (option `--report`). Contient :

- Nombre total de dossiers extraits
- Tableau **marque × concession × nb_dossiers**
- **Marques détectées hors mapping n8n v1** (ex: Citroën, Volkswagen…) — liste explicite avec volume
- Concessions détectées hors mapping (faute de frappe SF, nouvelles concessions)
- Distribution des types de fichiers : `BDC*`, `Contrat*`, `CNI*`, `Scan_*`, `scanner@*`, etc.
- Taille moyenne d'un dossier (en Mo)
- Couples `(marque, concession)` sous-représentés (<10 dossiers) → à signaler

## Étape 3 — `scripts/analyze_dataset.py`

### Comportement

```bash
# Échantillonner et analyser 10 dossiers par couple (marque, concession)
python scripts/analyze_dataset.py --sample-per-pair 10

# Limiter à une marque
python scripts/analyze_dataset.py --marque renault --sample-per-pair 20

# Sans appel Gemini (juste stats sur les types détectés)
python scripts/analyze_dataset.py --no-llm
```

### Prompt Gemini OUVERT (très important)

⚠️ **Ce prompt est délibérément ouvert** : on ne lui donne PAS le schéma de production. On veut découvrir les patterns. Phase 2 affinera.

```
Tu es un assistant d'analyse documentaire. On te transmet une page (ou un document multi-pages) issu d'un dossier client de leasing automobile.

Tâche :
1. Identifie le type de document parmi : bon de commande, contrat de location, carte d'identité, permis de conduire, justificatif de domicile, avis d'imposition, attestation, carte grise, photo véhicule, géoportail, RIB, autre.
2. Décris en 5-10 lignes les éléments caractéristiques de ce document : libellés, sections, mentions, mise en page, logo / marque, présence de signatures, présence de cases à cocher.
3. Si c'est un BDC ou un contrat : liste TOUS les libellés exacts utilisés pour : prix HT, prix TTC, loyer mensuel, loyer hors options, durée, kilométrage, frais (mise à la route, immatriculation, pack livraison, etc.), nature du document (achat / location).
4. Note tout élément qui te surprend ou qui semble propre à cette marque / concession (mention atypique, logo de filiale financière, formulaire spécifique).

Réponds en JSON :
{
  "type_document": "...",
  "description": "...",
  "marque_logo_detectee": "...",
  "libelles_cles": { ... },
  "particularites": [...]
}
```

### Sortie

`dataset/exploration_qualitative.jsonl` : 1 ligne par PDF analysé.

```json
{
  "opportunity_id": "0061x000ABC123XYZ",
  "marque": "fiat",
  "concession": "Fiat Belfort",
  "file_name": "BDC_signe.pdf",
  "type_document": "bon de commande",
  "description": "...",
  "marque_logo_detectee": "Fiat",
  "libelles_cles": {
    "prix_ttc": "Prix TTC véhicule",
    "loyer_hors_options": "Loyer mensuel hors prestations annexes",
    "nature": "Type d'opération",
    ...
  },
  "particularites": [
    "Case à cocher 'Achat / Location' en page 1",
    "Logo Stellantis Financial Services en pied de page"
  ]
}
```

### Limites de coût

- Budget cible : < 50 € pour toute la Phase 1 (Gemini 2.5 Pro)
- ~10 dossiers × 60 couples = 600 dossiers × ~8 PDFs = ~4800 appels Gemini
- À taux moyen ~0,005 € / appel → ~25 €
- Buffer 2x pour itérations → 50 €
- Si dépassement : limiter à 5 dossiers par couple, prioriser les couples à fort volume

## Étape 4 — `dossier-formats-par-marque.md` (humain)

Synthèse écrite **à la main** à partir de `exploration_qualitative.jsonl` (Renzo / Aurélien / Alexandre + Tiffany). Structure :

```markdown
# Fiat

## Format BDC
- Mise en page : ...
- Libellés clés :
  - Prix TTC : "Prix TTC véhicule"
  - Loyer hors options : "Loyer mensuel hors prestations annexes"
  - Nature : "Type d'opération" (case à cocher : "Achat" / "Location")
- Sections : 1. Identification / 2. Véhicule / 3. Prix et financement / 4. Signatures
- Particularités :
  - Logo Stellantis Financial Services
  - Mention "Aide au leasing social d'une voiture particulière électrique" obligatoire en cadre encadré

## Format Contrat
...

## Particularités par concession
- **Fiat Mulhouse** : utilise un BDC v2 (nouveau template depuis nov. 2025), libellé "Prix toutes taxes comprises" au lieu de "Prix TTC". → Prompt à surcharger.
- **Fiat Dijon** : mutualisé avec Jeep, prompt commun OK.

---

# Renault
...
```

Ce document **est** le matériau d'entrée de la Phase 2 (écriture des prompts).

## Critères de fin Phase 1

- [ ] ≥ 50 dossiers extraits par marque représentée (ou tous si <50)
- [ ] `dataset-stats.md` rempli, marques inconnues identifiées
- [ ] `dossier-formats-par-marque.md` rempli pour toutes les marques détectées
- [ ] Liste finalisée des couples `(marque, concession)` qui nécessitent une surcharge prompt en Phase 2
- [ ] Test set (20 dossiers/marque) et validation set (20 autres) splittés et figés
- [ ] Les 10 cas anomalies v1 du PDF (cf `ameliorations-v2.md` §1) localisés dans le dataset (ou reproduits si non retrouvés)

## Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Quota API Salesforce dépassé | Batch nocturne étalé, curseur sur CloseDate, retry exponentiel |
| Coût IA explose en exploration | Échantillonnage par couple, prompt court (60 lignes max), Gemini 2.5 Pro seulement si nécessaire (sinon Flash en exploration) |
| PDFs en clair sur disque | Chiffrement Fernet systématique, clé en `.env` (jamais commitée), purge post-Phase 1 |
| Mapping concessions incomplet | Le script log toutes les concessions vues mais absentes du mapping → revue manuelle |
| Dossiers `Closed Won` avec faux positifs (vrais non-conformes mais validés) | Considéré comme noise tolérable pour l'étude qualitative ; le backtest Phase 4 fera la vérité métier |
