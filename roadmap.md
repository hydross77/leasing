# Roadmap

> Phases détaillées avec livrables. À mettre à jour en cochant les items terminés au fur et à mesure.

**Estimation globale** : 4 à 6 semaines pour un système robuste à 1000 dossiers/jour, en travail focused.

---

## Phase 0 — Cadrage et setup projet 🚧

**Objectif** : avoir une base de code prête, des docs alignées et l'infra de dev opérationnelle.

**Durée estimée** : 1 à 2 jours.

### Livrables

- [x] Documents de cadrage (`CLAUDE.md`, `README.md`, `docs/*`)
- [ ] Repo Git initialisé + premier commit + push GitHub
- [ ] Projet FastAPI initialisé (`pyproject.toml`, structure de dossiers, healthcheck)
- [ ] `.env.example` complet
- [ ] `.gitignore` (Python + secrets)
- [ ] Compte Supabase créé + projet `leasing-prod` provisionné
- [ ] Tables BDD créées (prompts, analyses, concessions) — voir `docs/architecture.md`
- [ ] Compte Render créé + service connecté au repo (build OK même si l'app ne fait rien encore)
- [ ] Sentry configuré (project Python)
- [ ] Premier déploiement Render qui répond `200 OK` sur `/health`

### Tâches détaillées
Voir [`tasks/phase-0-setup.md`](../tasks/phase-0-setup.md).

---

## Phase 1 — Extraction du dataset des dossiers gagnés ⏳

**Objectif** : récupérer les dossiers déjà validés sur Salesforce (source de vérité) pour faire de l'**analyse exploratoire** et construire les prompts en Phase 2 par rétro-ingénierie sur les données réelles. **Aucun prompt de production n'est écrit en Phase 1.**

**Durée estimée** : 3 à 5 jours.

### Pré-requis
- Accès API Salesforce (OAuth) avec quota suffisant — ou batch nocturne étalé
- Validation DPO/RGPD pour stockage temporaire local chiffré des PDFs (cf ADR-004 exception)
- Phase 0 terminée (FastAPI healthcheck OK, Supabase provisionné)

### Livrables

- [ ] Script `scripts/extract_won_dossiers.py` :
  - Connexion SF (OAuth Username-Password ou JWT)
  - Requête SOQL : opportunités `StageName = 'Closed Won'` + `Leasing_electrique__c = TRUE` sur 12 derniers mois
  - Pour chaque opp : récupération de tous les `NEILON__File__c` associés via presigned URL
  - **Classement local par couple `(marque, concession, opportunity_id)`** (1 dossier = 1 dossier disque)
  - Chiffrement local des PDFs (script utilise `cryptography` ; clé dans `.env`, non commitée)
  - Métadonnées exportées en `dataset/metadata.jsonl` (1 ligne par dossier) : `opportunity_id`, `name`, `marque`, `concession`, `closed_date`, `nb_files`, `file_names`, `file_sizes`, `total_size_mb`
  - Idempotent : skip les dossiers déjà téléchargés (fichier `.lock` par opp)
- [ ] Stats par marque/concession dans `dataset-stats.md` :
  - Nombre de dossiers gagnés par marque ET par concession
  - **Marques inconnues** (présentes en SF mais absentes du mapping n8n) listées explicitement
  - Nombre moyen de PDFs par dossier
  - Distribution des types de noms de fichiers (`BDC*`, `Scan_*`, `scanner@*`, etc.)
  - Taille moyenne en Mo
- [ ] Script `scripts/analyze_dataset.py` :
  - Échantillonnage de 10-20 dossiers par couple (marque, concession) — ou tous si < 10
  - Premier passage Gemini 2.5 Pro avec **prompt très ouvert** : "Décris ce document, identifie son type, ses sections, ses libellés caractéristiques, les éventuelles spécificités de mise en page"
  - Sortie : `dataset/exploration_qualitative.jsonl` (1 ligne par PDF) + `dataset/exploration_summary.md` (synthèse humaine-lisible)
- [ ] Document `dossier-formats-par-marque.md` (synthèse humaine) :
  - Pour chaque couple (marque, concession) suffisamment représenté : libellés clés sur BDC/contrat, sections, mentions, particularités
  - Identification des concessions qui ont un BDC vraiment différent des autres de leur marque → liste des **surcharges concession** à prévoir en Phase 2
  - Identification des marques absentes du mapping n8n v1 et leur volume

### Critères de succès
- Au moins 50 dossiers gagnés par marque récupérés (ou tous si <50)
- Cartographie claire des types de pièces présents par marque ET par concession
- Liste finale des couples `(marque, concession)` à couvrir en prompts Phase 2

### Cible test set / validation set Phase 4
À l'issue de Phase 1, splitter le dataset :
- **Test set** : 20 dossiers/marque pour itération de prompts (Phase 2)
- **Validation set** : 20 autres/marque, jamais touchés en Phase 2 (sert au backtest Phase 4)
- **Cas anomalies v1** : les 10 cas listés dans `ameliorations-v2.md` section 1 doivent être inclus comme **non-régression obligatoire**

---

## Phase 2 — Construction des prompts par couple marque/concession ⏳

**Objectif** : produire les prompts de production, validés sur le test set Phase 1.

**Durée estimée** : 5 à 7 jours.

**Pré-requis** : Phase 1 terminée — étude qualitative effectuée. Pas d'écriture de prompt sans étude préalable.

### Stratégie cascade (cf ADR-005)

Hiérarchie de résolution au runtime : `(marque, concession)` → `(marque, NULL)` → `('default', NULL)`. On écrit donc le **minimum nécessaire** :

- **1 prompt `default`** par type (extraction_bdc, extraction_contrat, extraction_pieces_admin) — fallback ultime
- **1 prompt par marque** identifiée en Phase 1 (~10-15 marques)
- **Surcharges concession** uniquement pour les concessions identifiées comme atypiques en Phase 1

### Livrables

- [ ] Prompts `extraction_bdc` et `extraction_contrat` par marque (×10 à 15)
- [ ] Prompts `extraction_bdc` et `extraction_contrat` `default` (fallback global)
- [ ] Surcharges concession ponctuelles (estimé 0-10 selon résultats Phase 1)
- [ ] Prompt `extraction_pieces_admin` (générique, ×1)
- [ ] Prompt `verification` (général, ×1) — à terme remplacé par code Python pur en Phase 3, mais on garde une baseline
- [ ] Prompt `mail_generation` (général, ×1)
- [ ] Tous les prompts insérés en base Supabase avec `actif = TRUE`, version 1
- [ ] Documentation `prompts-strategy.md` :
  - Stratégie cascade appliquée
  - Spécificités identifiées par marque/concession
  - Cas limites connus à surveiller (notamment les 10 anomalies v1 de `ameliorations-v2.md`)

### Méthode

Pour chaque marque :
1. Sélectionner 20 dossiers gagnés (test set) et 20 autres (validation set, à ne pas toucher)
2. Examiner manuellement BDC + contrat : libellés, sections, mentions, **cases à cocher (location vs achat)**, **distinction loyer hors/avec options**
3. Écrire le prompt en s'appuyant sur le prompt v1 (cf `N8N.txt` node "Analyze document") + spécificités marque
4. **Inclure des consignes anti-anomalies v1** :
   - Toujours extraire `prix_ttc` (jamais déduire du HT)
   - Toujours extraire `loyer_hors_option` ET `loyer_avec_option` séparément
   - Toujours retourner `nature_bdc: "location" | "achat" | null` d'après la case cochée
   - Détailler les frais avec leur libellé (typage : autorisé / interdit fait en aval)
5. Tester sur les 20 dossiers test, mesurer la qualité d'extraction (manuel)
6. Itérer jusqu'à atteindre >90 % d'extraction correcte sur le test set
7. Valider sur le validation set (pas de modif du prompt sur ce set)

### Critères de succès
- Sur le validation set, >90 % des champs critiques (prix HT/TTC, date livraison, signatures, loyer hors/avec options, nature BDC, durée) correctement extraits
- Zéro hallucination majeure (champ inventé)
- Les 10 cas d'anomalies v1 (cf `ameliorations-v2.md` §1) ne déclenchent plus de faux positif

---

## Phase 3 — API et règles métier ASP 2025 ⏳

**Objectif** : implémenter l'API FastAPI complète avec règles métier testées.

**Durée estimée** : 3 à 5 jours.

### Livrables

- [ ] Endpoint `POST /analyze` opérationnel
- [ ] Service `extraction.py` : appel Gemini avec prompt dynamique par marque, validation Pydantic, retry
- [ ] Service `verification.py` : règles ASP 2025 en Python pur, **100 % testé unitairement**
- [ ] Service `confidence.py` : calcul indice de confiance
- [ ] Service `mail_html.py` : génération HTML conforme charte HESS
- [ ] Repository pattern pour Supabase (`services/supabase_client.py`)
- [ ] Logging structuré (structlog) sur tous les endpoints
- [ ] Sentry actif
- [ ] Tests unitaires sur :
  - Chaque règle ASP (un test par règle, cas conforme + cas non conforme)
  - Calcul indice de confiance
  - Validation des schémas Pydantic
- [ ] Documentation OpenAPI auto-générée accessible sur `/docs`

### Tests minimum requis
Liste non exhaustive — voir `glossaire.md` pour toutes les règles :

**Règles ASP de base**
- [ ] Test : RFR/part > 16 300 → non conforme
- [ ] Test : aide > 27 % **TTC** (jamais HT) → non conforme
- [ ] Test : géoportail mode "Plus rapide" → non conforme
- [ ] Test : durée location < 36 mois → non conforme
- [ ] Test : loyer **hors options** ≥ 200 € → non conforme (test bug v1 : loyer avec options doit être ignoré ici)
- [ ] Test : mention "Bonus écologique" sur BDC → non conforme
- [ ] Test : permis nouveau format expiré avant livraison → non conforme
- [ ] Test : justificatif domicile > 3 mois → non conforme
- [ ] Test : justificatif domicile = facture mobile → non conforme
- [ ] Test : photo VIN manquante → non conforme
- [ ] Test : délai BDC → livraison > 6 mois → non conforme

**Règles contrôle loyer renforcé (PDF v2 §2.3)**
- [ ] Test : 1ère mensualité avant déduction aide ≠ montant aide BDC → anomalie
- [ ] Test : 1ère mensualité après déduction aide ≠ 0 → anomalie
- [ ] Test : mensualités ultérieures ≠ loyer hors options du contrat → anomalie
- [ ] Test : mensualités ultérieures > 200 € → anomalie

**Frais autorisés (PDF v2 §A6)**
- [ ] Test : présence de "frais de mise à la route" → conforme
- [ ] Test : présence de "frais d'immatriculation" → conforme (régression bug v1)
- [ ] Test : présence de "pack livraison" → conforme (régression bug v1)
- [ ] Test : présence de "frais administratifs" pure → non conforme

**Non-régression anomalies v1** (cf `ameliorations-v2.md` §1)
- [ ] Test A1 : RFR/parts conforme → pas d'alerte
- [ ] Test A4 : BDC avec prix TTC présent → pas d'alerte "prix TTC manquant"
- [ ] Test A5 : aide 7000 € sur véhicule 26000 € TTC (= 26,9 %) → conforme (et non 7000 € / HT)
- [ ] Test A9 : BDC case "location" cochée → `nature_bdc = "location"`
- [ ] Test A10 : loyer 196,96 € hors options + 268,14 € avec options → conforme

---

## Phase 4 — Backtesting sur dossiers gagnés ⏳

**Objectif** : valider la précision du système sur des données réelles avant mise en prod.

**Durée estimée** : 2 à 3 jours.

### Livrables

- [ ] Script `scripts/backtest.py` :
  - Itère sur 100-200 dossiers gagnés par marque
  - Appelle l'endpoint `/analyze` local
  - Compare verdict avec vérité terrain (= conforme par définition, ces dossiers ont gagné)
  - Stocke les résultats en base ou CSV
- [ ] Métriques calculées :
  - Taux de vrais positifs (dossier gagné → verdict conforme) : **cible >95 %**
  - Taux de faux négatifs (dossier gagné → verdict non conforme) : **cible <5 %**
  - Taux d'erreur technique : **cible <2 %**
  - Précision par marque
  - Précision par règle (laquelle déclenche le plus de faux négatifs)
- [ ] Si des dossiers refusés ASP sont accessibles : tester aussi le rappel (refusé → verdict non conforme)
- [ ] Documentation `docs/backtest-results.md` avec :
  - Métriques globales et par marque
  - Liste des cas problématiques avec analyse
  - Recommandations d'ajustement (prompts, règles, seuils)

### Critère bloquant pour passer en prod
**>95 % de précision globale sur le backtest, sans aucun dossier gagné déclaré non conforme à cause d'une règle trop stricte.**

Si la précision est en dessous : retour Phase 2/3 pour itérer sur prompts ou règles.

---

## Phase 5 — Intégration n8n + déploiement Render ⏳

**Objectif** : connecter le tout en environnement de production, en parallèle de l'ancien workflow (shadow mode). **n8n = orchestration / flux général ; le code projet = backend métier.**

**Durée estimée** : 2 à 3 jours.

### Livrables côté n8n

- [ ] Nouveau workflow `Leasing_v2` créé (sans toucher au v1 qui tourne en prod)
- [ ] Schedule trigger (toutes les 1-2 min — le v1 actuel toutes les 4s est trop agressif)
- [ ] Lecture opportunités à traiter (SOQL existante v1 réutilisée)
- [ ] **Verrouillage immédiat** : update SF `Statut_traitement__c = 'En cours'` AVANT analyse
- [ ] Sub-workflow `Traiter_dossier` :
  - Appel HTTP `POST /analyze` vers l'API FastAPI (Bearer token)
  - Routage selon verdict (conforme / non_conforme / erreur_technique / aucun_doc)
  - Envoi mail(s) Gmail (TO concession depuis le `mail.destinataire_principal` retourné par l'API ; CC Renzo + Aurélien + Alexandre)
  - **Renommage SF des fichiers anonymes** : si l'API renvoie `renommage_pieces`, patch `NEILON__File__c.Name` (cf `ameliorations-v2.md` §2.5)
  - Update SF final : `Tech_Dossier_verifier__c`, `Conformite_du_dossier__c`, `Date_livraison_definitive__c`
- [ ] Mode shadow : v2 tourne mais **n'envoie pas de mail** au début, seulement log les verdicts pour comparaison avec v1

### Human-in-the-loop pour les non_conformes (ADR-013)

- [ ] Nouveau champ SF `Statut_validation_humaine__c` (picklist)
- [ ] Workflow `Leasing_v2` route les `non_conforme` vers mail interne **uniquement** (pas de mail concession à ce stade)
- [ ] Mail interne avec 2 liens cliquables : `Approuver` (déclenche envoi concession) / `Rejeter` (log + retour en attente)
- [ ] Endpoint API ou webhook n8n `POST /validation/{opportunity_id}` pour traiter la décision
- [ ] Workflow secondaire `Leasing_v2_envoi_concession` déclenché sur `validée`
- [ ] Reporting : taux de rejet humain par marque / concession → indicateur de qualité IA

### Workflows annexes Phase 5 (depuis PDF v2)

- [ ] **Workflow `Leasing_v2_relances_6mois`** (cf `ameliorations-v2.md` §2.2) :
  - Schedule quotidien
  - SOQL : opportunités où `BDC_signe_le__c` < `today - 5 mois` ET `Date_livraison_definitive__c` IS NULL
  - Envoi mail d'alerte à la concession + Renzo
- [ ] **Workflow `Leasing_v2_relances_post_livraison`** (cf `ameliorations-v2.md` §2.1) :
  - Schedule quotidien
  - SOQL : opportunités en statut `livré` depuis ≥ 7 jours sans documents post-livraison reçus
  - Envoi mail liste des pièces manquantes (facture vente, carte grise, photo VIN, photo arrière, attestations finales)
- [ ] **Nouveau statut SF `livré`** (cf `ameliorations-v2.md` §2.4) :
  - Ajouter la valeur de picklist sur `Conformite_du_dossier__c` ou champ dédié
  - Synchronisation ICAR → SF (hors API, sujet n8n + SF)

### Livrables côté API

- [ ] Variables d'environnement Render configurées
- [ ] Domaine custom (optionnel) ou URL Render publique sécurisée par token
- [ ] Endpoint protégé par Bearer token (clé partagée avec n8n)
- [ ] Logs vérifiés en prod
- [ ] Sentry connecté

### Tests d'intégration
- [ ] Test bout-en-bout sur 10 vrais dossiers en shadow
- [ ] Vérification : verdicts v2 cohérents avec v1 (ou meilleurs)
- [ ] Vérification : mails générés correctement (sans envoi)

---

## Phase 6 — Roll-out progressif en production ⏳

**Objectif** : basculer progressivement v2 → v1 par marque, avec monitoring intensif.

**Durée estimée** : 1 à 2 semaines.

### Étapes

- [ ] **Semaine 1 — Pilote sur 1 marque** :
  - Choisir une marque à volume modéré (ex: Fiat ou Toyota)
  - v2 envoie les vrais mails pour cette marque
  - v1 désactivé pour cette marque
  - Monitoring quotidien : taux de conformité, anomalies, plaintes vendeurs
  - Itération si besoin

- [ ] **Semaine 2 — Extension** :
  - +2 marques par jour si pilote OK
  - Continuer le monitoring
  - Ajustements de prompts à chaud (bénéfice de l'archi BDD)

- [ ] **Fin de roll-out** :
  - Toutes les marques sur v2
  - v1 désactivé puis archivé
  - Bilan post-mortem : performance, coûts, fiabilité

### Critères Go/No-Go par marque

Avant chaque ajout de marque :
- ✅ Précision pilote >95 % observée pendant 3 jours pleins
- ✅ Aucune plainte vendeur ou concession sur la marque pilote
- ✅ Coût IA dans le budget prévu
- ✅ Aucune erreur Sentry critique

Si un seul de ces critères est rouge → on attend, on debugge, on n'ajoute pas de marque.

---

## Indicateurs de suivi (à monitorer en continu post-MVP)

| Métrique | Cible | Alerting |
|----------|-------|----------|
| Latence p95 `/analyze` | <60s | >120s |
| Taux d'erreurs Sentry | <1% | >5% |
| Taux d'erreurs techniques (verdict `erreur_technique`) | <2% | >5% |
| Taux de validation sur dossiers gagnés | >95% | <90% |
| Coût IA / dossier | <0,30 € | >0,50 € |
| Volumétrie quotidienne | ~1000 | écart >30% |

---

## Backlog (post-MVP)

Idées à garder pour plus tard :
- Cache Redis des analyses récentes
- Dashboard Streamlit ou Metabase pour monitoring temps réel
- Pré-classification rapide du type de doc (CNI / BDC / etc.) avec un petit modèle, avant Gemini → économie tokens
- Webhook SF direct (sans n8n) en alternative
- Fine-tuning d'un modèle Gemini sur dataset HESS
- Multi-environnement (staging séparé de prod)
- Tests de charge automatisés (k6 ou Locust)
