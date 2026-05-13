# Décisions architecturales (ADR)

> Chaque décision technique non triviale est tracée ici avec son contexte, les alternatives considérées et la justification. Format inspiré des ADR (Architecture Decision Records).

---

## ADR-001 — Séparer la logique métier de n8n dans une API Python dédiée

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Le workflow n8n existant accumule ~15 Code nodes JavaScript pour gérer le parsing JSON Gemini, les règles métier ASP, la génération HTML, le mapping concessions. Il n'est ni testable, ni versionnable proprement, ni maintenable à 1000 dossiers/jour.

### Décision
Extraire toute la logique métier dans une API FastAPI Python séparée. n8n garde uniquement l'orchestration (trigger, Salesforce, Gmail).

### Alternatives considérées
- **Garder tout en n8n** : impossible à maintenir à terme, risque de régression à chaque modif
- **Cloud Functions (GCP / AWS Lambda)** : viable mais ajoute de la complexité pour démarrer
- **Service Node.js** : cohérent avec n8n (JS partout) mais écosystème PDF/IA Python supérieur

### Conséquences
- ➕ Code testable, versionné, déployable indépendamment
- ➕ Bibliothèques Python (pdfplumber, Pillow, Pydantic) bien plus puissantes
- ➕ Réutilisable depuis d'autres orchestrateurs si on quitte n8n un jour
- ➖ Une infra de plus à maintenir (Render)
- ➖ Latence supplémentaire (n8n → API), négligeable en pratique (<200ms)

---

## ADR-002 — Python + FastAPI plutôt que Node + Fastify

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Choix du langage pour l'API métier.

### Décision
Python 3.12 + FastAPI.

### Justification
- Écosystème IA et PDF mature (google-generativeai, openai SDK natifs, pdfplumber)
- Pydantic v2 = validation stricte des sorties IA (résout le problème principal du workflow actuel : JSON Gemini non fiable)
- FastAPI génère automatiquement la doc OpenAPI, utile pour n8n
- Type hints + mypy = robustesse sur les règles métier critiques
- Communauté + StackOverflow sur les use cases similaires (analyse de docs administratifs)

### Conséquences
- ➕ Velocity de développement sur la partie IA
- ➖ L'équipe doit maintenir un langage en plus de JS (n8n) si elle n'est pas Python

---

## ADR-003 — Supabase (PostgreSQL managé) pour la base technique

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Besoin de stocker : prompts versionnés éditables à chaud, historique des analyses pour monitoring, mapping concessions.

### Décision
Supabase (free tier au démarrage).

### Alternatives considérées
- **Fichiers Markdown dans Git** pour les prompts : pas d'édition à chaud, oblige à redéployer pour chaque ajustement → rejeté car les règles vont bouger souvent
- **Salesforce custom objects** : pollue le schéma métier SF, lent en lecture, quotas API consommés → rejeté
- **Render Postgres** : payant dès le début, moins d'outils UI que Supabase
- **SQLite** : pas de scaling, pas d'édition distante

### Justification
- UI Supabase pour éditer les prompts directement (utilisable par non-dev)
- Free tier 500 Mo + 2 Go de bande passante / mois → suffit largement
- PostgreSQL natif, on garde la portabilité (migration possible vers Render Postgres ou autre plus tard)
- Row-level security si besoin de multi-utilisateurs

---

## ADR-004 — Pas de stockage persistant des PDFs

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Les PDFs contiennent des données très sensibles (CNI, avis d'imposition, RIB, justificatifs domicile). Risque RGPD majeur en cas de fuite.

### Décision
Aucun PDF stocké sur disque ni dans le cloud. Streaming depuis presigned URLs Salesforce → analyse en RAM → résultat JSON en base → PDF en mémoire jeté en fin de requête.

### Conséquences
- ➕ Conformité RGPD facilitée (aucune donnée perso persistée hors SF)
- ➕ Aucun coût de stockage
- ➕ Salesforce reste la seule source de vérité
- ➖ En cas de retry après crash, on doit re-télécharger le PDF (négligeable, presigned URLs durables)
- ➖ Pas de cache possible (mais peu d'analyses sont rejouées)

### Exception
Pendant la **phase d'analyse rétrospective** (Phase 1 du roadmap), on télécharge temporairement les PDFs des dossiers gagnés en local pour étudier les patterns. Stockage chiffré sur disque local du développeur uniquement, suppression à la fin de la phase. À documenter et faire valider par le DPO HESS si nécessaire.

---

## ADR-005 — Prompts par couple `(marque, concession)` avec cascade de fallback

**Date** : 2026-05-13 (rév. 2026-05-13 — granularité concession ajoutée)
**Statut** : Acceptée

### Contexte
Chaque marque (Fiat, Hyundai, Renault, etc.) a un BDC et un contrat de location avec une mise en page propre. Un prompt unique générique force Gemini à deviner, ce qui dégrade l'extraction. Par ailleurs, au sein d'une même marque, certaines concessions peuvent avoir des particularités (cachet, version d'éditeur, mentions ajoutées). HESS gère 10 à 15 marques pour ~55-60 concessions.

### Décision
Stocker les prompts en base avec une clé composée `(marque, concession, type_prompt)`. La résolution au chargement suit une **cascade à 3 niveaux** :

1. **Surcharge concession** : `(marque=M, concession=C, type_prompt=T)` — quand une concession a un format atypique
2. **Fallback marque** : `(marque=M, concession=NULL, type_prompt=T)` — défaut pour toutes les concessions de la marque
3. **Fallback global** : `(marque='default', concession=NULL, type_prompt=T)` — sécurité quand une marque n'est pas couverte (nouvelle marque, marque hors mapping)

Le fallback global garantit qu'aucun dossier ne sort sans prompt — la qualité dégrade gracieusement plutôt que de planter.

### Stratégie de production (Phase 2)
- **Phase 2 démarrage** : créer un prompt par marque (~10-15 prompts marque) + 1 prompt `default` + 1 prompt `pieces_admin` générique + 1 prompt `verification` + 1 prompt `mail_generation`
- **Phase 2 raffinement** : si le backtest (Phase 4) révèle une concession qui sous-performe, créer une surcharge `(marque, concession)` ciblée
- **Total estimé en MVP** : ~15-20 prompts ; à terme, jusqu'à ~30-40 si certaines concessions ont leurs particularités

### Types de prompts
- `extraction_bdc` — extraction du bon de commande
- `extraction_contrat` — extraction du contrat de location
- `extraction_pieces_admin` — extraction des pièces administratives (CNI, avis imposition, justif domicile, etc.) — généralement le prompt `default` suffit
- `verification` — règles ASP 2025 (porté en code Python pur en Phase 3, cf ADR-007)
- `mail_generation` — génération HTML mail

### Avantages
- Précision d'extraction +++ par marque
- Tokens consommés divisés par 2-3 (prompts plus courts car spécialisés)
- Maintenance ciblée : modif Fiat n'impacte pas Hyundai, modif Fiat Mulhouse n'impacte pas Fiat Belfort
- Pas de duplication : on n'écrit une surcharge concession que si elle est nécessaire
- Aucun dossier ne plante par manque de prompt (fallback global garanti)

---

## ADR-006 — Gemini 2.5 Pro maintenu pour l'extraction critique

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Question initiale : passer en partie sur Gemini Flash pour économiser. Décision après feedback Renzo : Flash se trompe trop sur les docs administratifs.

### Décision
Gemini 2.5 Pro pour toutes les extractions, sans bascule Flash pour l'instant.

### À revisiter
Si le backtest (Phase 4) montre que Flash est suffisant sur certaines pièces simples (justificatif de domicile par exemple), on pourra basculer ces pièces en Flash. À mesurer.

### Coût estimé
À 1000 dossiers/jour × 8 PDFs en moyenne × Gemini Pro : entre 200 et 400 €/jour selon la taille des prompts. À optimiser via :
- Prompts plus courts (spécialisation par marque)
- Compression des images PDF avant envoi (résolution adaptée)
- Cache des analyses récentes (peu probable mais possible)

---

## ADR-007 — OpenAI conservé pour vérification + génération mail

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Le workflow actuel utilise GPT-5-mini pour la vérification et GPT-4 pour la génération de mail.

### Décision
Garder OpenAI mais :
- **GPT-5-mini** pour la vérification de conformité (raisonnement structuré, bon rapport qualité/prix)
- **GPT-5-mini** aussi pour la génération de mail (GPT-4 legacy est trop cher et plus pertinent)

### Note
Pour la vérification, on pourrait à terme la passer en code Python pur (déterministe, testable, gratuit). C'est même conseillé. Mais en MVP on garde le modèle pour gérer les cas limites avec nuance. À refactorer en pur code Python si on observe trop de variabilité.

---

## ADR-008 — Déploiement sur Render

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Choix de l'hébergement de l'API.

### Décision
Render Web Service (région Frankfurt).

### Alternatives
- **Railway** : équivalent fonctionnel, peu de différence
- **Fly.io** : moins cher en scaling, plus technique à setup
- **AWS/GCP** : surdimensionné pour démarrer

### Justification
- Auto-deploy depuis GitHub
- ~7 €/mois pour un Starter (suffisant en MVP)
- Logs intégrés
- Healthchecks automatiques
- Frankfurt = latence basse vers Salesforce EU et clients HESS (France)

---

## ADR-009 — Validation Pydantic stricte sur toutes les sorties IA

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Le workflow n8n actuel parse les sorties Gemini avec `JSON.parse(text)` dans un Code node, avec gestion d'erreur basique. C'est la source #1 de bugs silencieux : un dossier vide peut être déclaré conforme.

### Décision
**Toute sortie d'IA passe par un modèle Pydantic strict.** Si la validation échoue :
1. Logger la réponse brute + le prompt utilisé
2. Retry 2x
3. Si échec persistant : verdict `erreur_technique`, traitement manuel forcé

Aucune logique métier ne touche jamais à un dict Python "brut" issu de l'IA.

### Conséquences
- ➕ Détection immédiate des dérives de format (hallucinations, champs manqués)
- ➕ Tests unitaires faciles à écrire sur les schémas
- ➕ Documentation OpenAPI auto-générée pour les schémas
- ➖ Un peu plus de code à écrire (modèles Pydantic à maintenir), largement compensé par la robustesse

---

## ADR-010 — Pas de webhook Salesforce direct (au moins pour MVP)

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
On pourrait imaginer un Outbound Message Salesforce qui appelle directement l'API à chaque opportunité prête. Plus réactif que le polling toutes les 1-2 min par n8n.

### Décision
Garder n8n en orchestrateur pour le MVP.

### Justification
- L'archi existante n8n est connue, fonctionne, on capitalise dessus
- Salesforce Outbound Messages = lock-in fort, plus complexe à debug
- Le polling 1-2 min est largement suffisant pour la SLA métier (pas d'urgence à la seconde)
- Si besoin de temps réel plus tard : ajouter un endpoint webhook sans casser l'existant

### À revisiter
Si on observe des pics de charge importants à certains moments de la journée, étudier un push SF → API direct.

---

## ADR-011 — Intégration des retours du PDF "Amélioration Leasing Social" dans la roadmap v2

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Un PDF de 3 pages (`Amélioration Leasing Social.pdf`) listant 10 anomalies du système v1 et 5 axes d'amélioration produit a été transmis par le manager. Ces retours doivent être intégrés à la conception v2 avant tout codage de prompts ou de règles métier.

### Décision
Documenter ces retours dans un fichier dédié [`ameliorations-v2.md`](ameliorations-v2.md) et les rattacher explicitement aux phases de la roadmap :
- **Phase 2** (prompts) et **Phase 3** (règles métier) : corriger les 10 anomalies (A1-A10)
- **Phase 4** (backtest) : inclure les 10 cas comme test set de **non-régression obligatoire**
- **Phase 5** (n8n) : nouvelles fonctionnalités relances + statut "livré" + renommage pièces

### Conséquences
- ➕ Aucune dérive : les retours sont tracés, rattachés à des livrables précis, mesurables au backtest
- ➕ Le PDF reste la référence d'origine, on ne le réinterprète pas après coup
- ➕ Le glossaire (`glossaire.md`) est mis à jour pour refléter les règles correctes (TTC ≠ HT, frais autorisés étendus, RIB/fiche paie retirés)
- ➖ Le périmètre Phase 5 grossit (3 workflows n8n au lieu d'1) ; estimation à revoir

### Items dérivés validés
- ADR-005 révisée pour cascade `(marque, concession) → marque → default`
- Glossaire : RIB retiré, frais autorisés étendus, règles loyer renforcé, délai 6 mois
- Roadmap Phase 2 : prompts par marque avec consignes anti-anomalies v1
- Roadmap Phase 3 : nouveaux tests unitaires (loyer 1ère mensualité, frais autorisés, non-régression v1)
- Roadmap Phase 5 : 2 workflows n8n supplémentaires + statut `livré`

---

## ADR-012 — Salesforce est la seule source de vérité métier ; Supabase ne stocke que de la technique

**Date** : 2026-05-13
**Statut** : Acceptée (rappel/consolidation des ADR-003 et ADR-004)

### Contexte
Avec l'arrivée de Supabase (prompts, analyses, concessions) dans l'archi, risque de duplication ou de dérive : on pourrait être tenté de stocker un sous-ensemble de la donnée client dans Supabase pour des raisons de performance ou de monitoring.

### Décision
**Aucune donnée métier ne quitte Salesforce.** Supabase contient uniquement :
- Prompts versionnés (technique)
- Historique d'analyses (technique, monitoring, RGPD : 90j de rétention)
- Mapping concessions (technique, change fréquemment)

Tout ce qui est opportunité, client, fichier joint, statut, date de livraison, vit en Salesforce et **seulement** en Salesforce. L'API lit depuis SF à chaque requête `/analyze` ; n8n écrit dans SF à chaque fin d'analyse.

### Conséquences
- ➕ Pas de divergence entre deux bases
- ➕ Conformité RGPD facilitée (cf ADR-004)
- ➕ Migration / changement d'orchestrateur facilités
- ➖ Si Salesforce tombe, l'API ne peut rien analyser — acceptable, c'est aussi vrai du workflow v1

---

## ADR-013 — Validation humaine obligatoire avant envoi mail concession sur les dossiers "non conforme"

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Le système v1 envoie automatiquement le mail "non conforme" à la concession (vendeur, secrétaire) **en même temps** que le mail interne à l'équipe HESS (cf `N8N.txt` nœuds `Maill non conforme` → CC interne et `Maill non conforme3` → concession). Conséquence : quand l'IA se trompe (cf les 10 anomalies du PDF v2), un mail erroné arrive chez le vendeur en temps réel. Cela détruit la crédibilité du système et alimente la défiance des concessions.

Tolérance au risque : un faux positif "non conforme" (= dossier conforme déclaré non-conforme) coûte cher en réputation. Un faux négatif (= dossier non conforme déclaré conforme) coûte cher financièrement (aide ASP versée à tort). Les deux doivent être minimisés.

### Décision
**Aucun mail "non conforme" n'est envoyé à la concession sans validation humaine préalable** par l'équipe HESS.

Flux v2 par verdict :

| Verdict | Mail concession | Mail interne | Validation humaine |
|---------|-----------------|--------------|--------------------|
| `conforme` | Direct | CC | Non |
| `non_conforme` | **Attendre validation** | TO (avec liens approuver/rejeter) | **Obligatoire** |
| `erreur_technique` | Aucun | TO | Manuel |
| `aucun_doc` | Aucun | TO | Manuel |

### Implémentation
- **Salesforce** : nouveau champ `Statut_validation_humaine__c` (picklist : `en_attente` / `validée` / `rejetée` / `non_applicable`)
- **n8n workflow `Leasing_v2`** : sur verdict `non_conforme`, mettre `Statut_validation_humaine__c = en_attente` et envoyer mail interne uniquement (TO Renzo + CC Aurélien/Alexandre) avec 2 boutons cliquables
- **API ou webhook n8n** : `POST /validation/{opportunity_id}` (avec token) accepte `decision: validée | rejetée` + raison libre
- **n8n workflow secondaire `Leasing_v2_envoi_concession`** : déclenché quand `Statut_validation_humaine__c = validée`, envoie le mail concession et update SF (`Conformite_du_dossier__c = "Document absent ou à corriger"`)
- **Si rejetée** : log la raison (champ SF dédié `Validation_humaine_raison__c`), pas de mail concession, le dossier retourne à `Statut_traitement__c = En attente`

### Conséquences
- ➕ Crédibilité préservée auprès des concessions : aucune erreur IA n'arrive chez le vendeur
- ➕ Boucle d'amélioration continue : les rejets humains alimentent un dataset pour itérer sur les prompts
- ➕ Reporting : taux de rejets humains = indicateur clé de la qualité IA
- ➖ Latence sur les non_conformes (humain dans la boucle = quelques heures)
- ➖ Charge équipe HESS au démarrage (à 1000 dossiers/jour, on peut s'attendre à ~50-150 non_conformes/jour à valider)

### Évolution prévue
- Phase de **shadow + validation 100%** au démarrage (toute la prod passe par l'humain)
- Quand backtest Phase 4 stabilise à >95% de précision pendant 4 semaines, possibilité de **bascule en auto pour les non_conformes haute confiance (indice ≥ 90%)** → seuls les `indice < 90%` passent par validation humaine
- Décision de bascule à acter en ADR séparée le moment venu, pas avant

---

## ADR-014 — Stratégie de typage des pièces uploadées : renommage IA d'abord, picklist SF ensuite

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Les concessions uploadent les pièces du dossier en vrac dans `NEILON__File__c` (lié à l'opportunité). Aucun champ ne distingue un BDC d'une CNI d'un justificatif de domicile. Conséquences :
- L'IA doit deviner le type (faux positifs A2, A3 du PDF v2 — pièce d'identité non détectée alors qu'elle est présente)
- L'équipe HESS perd du temps à fouiller pour vérifier
- Pas de croisement possible entre intention vendeur et détection IA

### Décision
Approche en 2 temps :

1. **Phase 3 (MVP) — Renommage IA des pièces** (déjà prévu §2.5 du PDF v2)
   - L'API détecte le type via Gemini (champ `type_document` déjà extrait)
   - L'API renvoie dans la réponse `/analyze` un mapping `{ file_id: nom_propose }`
   - n8n patche `NEILON__File__c.Name` (ex: `Scan_20251001_092559.pdf` → `BDC.pdf`)
   - Aucun changement côté vendeur, gain immédiat de lisibilité

2. **Post-MVP — Picklist `Type_document__c` sur `NEILON__File__c`** (sujet Salesforce admin, hors API)
   - Création du champ picklist : `BDC / Contrat / CNI / Permis / Justif domicile / Avis imposition / Attestation gros rouleur / Attestation respect engagements / Attestation respect loyers / Géoportail / Carte grise / Photo VIN / Photo arrière / Photo macaron / Fiche restitution / RIB (facultatif) / autre`
   - Pré-rempli automatiquement par l'IA via API (extension du renommage)
   - Modifiable par le vendeur s'il a connaissance d'une mauvaise classification
   - L'API croise type déclaré (champ) vs type détecté (Gemini) — écart = alerte interne

### Alternatives écartées (pour le moment)
- **Champs lookup dédiés sur Opportunity** (`Fichier_BDC__c`, `Fichier_CNI__c`…) : refonte UX SF lourde, formation concessions nécessaire, gain marginal vs picklist
- **Sections obligatoires dans le formulaire d'upload** : équivalent UX au précédent, complexe à maintenir si l'ASP fait évoluer la liste des pièces

### Conséquences
- ➕ Court terme : amélioration immédiate sans demander aux concessions de changer leurs habitudes ("bourrin" = upload en vrac, on s'adapte)
- ➕ Moyen terme : double validation (humain + IA), dataset propre pour fine-tuning futur
- ➕ Si l'IA classe mal (ex: confond justif domicile et avis imposition), le vendeur peut corriger
- ➖ Phase 3 : un dossier qui n'a aucun nom propre dépend 100% de l'IA pour le classement → si l'IA se trompe, on perd du temps
- ➖ Post-MVP : ajouter le picklist nécessite Salesforce admin (Renzo + équipe SF) ; à planifier

### Note sur le RIB
Le RIB ayant été retiré des obligatoires (cf `glossaire.md` et PDF v2 page 3), son absence de champ dédié n'est pas un problème prioritaire. Idem fiche de paie.

---

## Template pour ajouter une nouvelle ADR

```markdown
## ADR-XXX — Titre court de la décision

**Date** : YYYY-MM-DD
**Statut** : Proposée / Acceptée / Refusée / Remplacée par ADR-YYY

### Contexte
Pourquoi cette décision est-elle nécessaire ?

### Décision
Ce qu'on a choisi.

### Alternatives considérées
Quoi d'autre ? Pourquoi pas ?

### Conséquences
Bonnes et mauvaises.
```
