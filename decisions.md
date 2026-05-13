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

## ADR-013 — Validation humaine systématique par le comptable avant tout envoi mail vendeur

**Date** : 2026-05-13 (rév. 2026-05-13 — extension aux verdicts conformes)
**Statut** : Acceptée

### Contexte
Le système v1 envoie automatiquement les mails à la concession (vendeur, secrétaire) en parallèle du mail interne (cf `N8N.txt` nœuds `Maill non conforme` → CC interne et `Maill non conforme3` → concession). Conséquence sur les 10 anomalies du PDF v2 : mails erronés en temps réel → crédibilité détruite.

De plus, **même un verdict `conforme` peut être faux** : si l'IA passe à côté d'une anomalie (faux négatif), un dossier non-conforme est validé → aide ASP versée à tort → reproche financier à HESS. Donc la validation humaine doit couvrir les **deux** cas.

Tolérance au risque :
- Faux positif `non_conforme` (dossier conforme déclaré non-conforme) → coût en réputation
- Faux négatif `conforme` (dossier non-conforme déclaré conforme) → coût financier ASP

Les deux doivent passer par un œil humain expert (le comptable HESS).

### Décision
**Aucun mail au vendeur/secrétaire ne part sans validation comptable préalable, peu importe le verdict IA.**

Flux v2 par verdict :

| Verdict IA | Mail vendeur direct ? | Validation comptable | Mail vendeur final |
|------------|------------------------|----------------------|---------------------|
| `conforme` | ❌ Non | **Obligatoire** | Si comptable confirme conforme : "OK conforme"<br>Si comptable détecte anomalie : "redéposer fichier en anomalie" |
| `non_conforme` | ❌ Non | **Obligatoire** | Si comptable confirme anomalie : "redéposer fichier en anomalie"<br>Si comptable inverse (faux positif IA) : "OK conforme" |
| `erreur_technique` | ❌ Non | Manuel | Traitement manuel HESS |
| `aucun_doc` | ❌ Non | Manuel | Mail vendeur "aucune pièce reçue" après validation |

### Outil de validation : Dashboard Comptable (cf ADR-016)

Plutôt que des emails de validation avec liens cliquables (~500/jour à 1000 dossiers/jour), le comptable utilise un **dashboard dédié** (Streamlit) où il peut :
- Voir tous les dossiers en attente de validation
- Ouvrir les PDFs du dossier
- Ajouter/retirer des anomalies (faux positifs/négatifs IA)
- Cliquer "Valider et envoyer" → déclenche mail vendeur avec la liste **finale** d'anomalies

### Implémentation
- **Salesforce** : nouveau champ `Statut_validation_humaine__c` (picklist : `en_attente` / `validée_conforme` / `validée_non_conforme` / `non_applicable`)
- **n8n workflow `Leasing_v2`** : sur tout verdict, mettre `Statut_validation_humaine__c = en_attente`, écrire l'analyse en base Supabase, **ne PAS envoyer de mail vendeur**
- **Dashboard comptable (Streamlit)** : liste les `analyses` où `statut_validation_humaine = en_attente`. Le comptable édite et clique "Valider".
- **API endpoint `POST /validation/{analyse_id}`** : reçoit `decision: conforme | non_conforme` + liste d'anomalies finales + raison. Met à jour Supabase + déclenche le webhook n8n pour mail vendeur + update SF.
- **n8n workflow secondaire `Leasing_v2_envoi_vendeur`** : déclenché par webhook, envoie le mail vendeur + cc concession + update SF final

### Conséquences
- ➕ Crédibilité préservée auprès des concessions
- ➕ Couverture des faux négatifs (pas seulement les faux positifs)
- ➕ Boucle d'amélioration : les corrections comptable = dataset doré pour itérer sur les prompts
- ➕ Métriques : taux d'accord IA/comptable par marque (indicateur de qualité prompt)
- ➖ Latence sur tous les verdicts (humain = quelques heures à quelques jours)
- ➖ Charge comptable : 1000 dossiers/jour à valider. Mais avec le dashboard et un bon taux d'accord IA (>80% espéré post Phase 4), le travail = 1-2 clics par dossier conforme, plus de temps sur les non_conformes.

### Évolution prévue
- Phase initiale : **100% des dossiers passent par le comptable** (sécurité maximale)
- Post backtest >95% stable : possibilité de **bypass auto pour les conformes haute confiance** (indice ≥ 95% + zéro anomalie critique détectée). Décision séparée à acter le moment venu.
- Les `non_conformes` continuent de passer systématiquement par le comptable (asymétrie volontaire : on prend plus de risque sur les conformes que sur les non_conformes)

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

## ADR-015 — Cycle de vie SF du dossier + ré-analyses sur changement de statut

**Date** : 2026-05-13 (rév. 2026-05-13 — écoute du statut, pas du fichier)
**Statut** : Acceptée

### Contexte
Quand l'IA + le comptable concluent que le dossier est en anomalie, le mail au vendeur dit "redéposer le fichier en anomalie sur Salesforce". **Le vendeur ne crée pas un nouveau dossier** — il modifie le dossier existant dans SF (corrige le fichier qui pose souci, change le statut). Notre système doit donc **écouter le statut SF du dossier**, pas seulement les modifications de fichiers individuels.

Par ailleurs, Salesforce ne supprime pas l'ancien `NEILON__File__c` quand le vendeur en uploade un nouveau : les deux coexistent. L'API doit dédupliquer côté Python pour ne garder que le plus récent par type de document.

### Décision

**1. Cycle de vie d'un dossier dans Salesforce** — nouveau champ picklist `Statut_dossier__c` sur `Opportunity` :

| Valeur | Sens | Qui la change | n8n re-déclenche `/analyze` ? |
|--------|------|---------------|--------------------------------|
| `nouveau` | Vendeur vient d'uploader, jamais analysé | Vendeur (à création) | ✅ Oui |
| `en_cours_analyse` | n8n a verrouillé pour traitement | n8n | Non (lui-même) |
| `en_attente_validation_comptable` | Analyse faite, attend le comptable dans le dashboard | API (après `/analyze`) | Non |
| `valide_conforme` | Comptable a validé, mail envoyé | Dashboard / API `/validation` | Non (FIN) |
| `en_anomalie_a_corriger` | Comptable a rejeté, mail envoyé au vendeur | Dashboard / API `/validation` | Non (attend vendeur) |
| `corrige_a_reverifier` | Vendeur a corrigé, demande ré-analyse | Vendeur (bouton SF) ou trigger auto | ✅ Oui |

**2. Trigger SF (sujet admin)** : à chaque changement de `Statut_dossier__c` vers `nouveau` ou `corrige_a_reverifier`, mettre `Tech_Dossier_verifier__c = FALSE` → le dossier réintègre la queue n8n.

**3. Action vendeur** : un bouton/UI custom dans SF "J'ai corrigé le dossier" qui passe `Statut_dossier__c` de `en_anomalie_a_corriger` → `corrige_a_reverifier`. **Optionnel** : un trigger qui automatise ce passage si un `NEILON__File__c` est modifié sur une opp en `en_anomalie_a_corriger`.

**4. Déduplication côté API** : analyser tous les `NEILON__File__c` reçus, mais au moment du verdict, ne garder que le plus récent par `type_document` détecté (basé sur `CreatedDate`). Tracer les doublons écartés dans le log d'analyse.

### Schéma simplifié

```
[nouveau / corrige_a_reverifier]
        ↓ trigger SF : Tech_Dossier_verifier__c = FALSE
        ↓
        n8n détecte → passe à [en_cours_analyse] → API /analyze
        ↓
        [en_attente_validation_comptable]
        ↓ Dashboard comptable clic
   ┌────┴────┐
   ↓         ↓
[valide]   [en_anomalie_a_corriger]
  FIN       ↓ Vendeur corrige + clique "J'ai corrigé"
            ↓
            [corrige_a_reverifier] → boucle au début
```

### Évolution progressive

- **Phase 5 (MVP)** : champ `Statut_dossier__c` + trigger SF + UI vendeur basique. Dédup côté API en gardant le plus récent par type Gemini.
- **Post-MVP** : si trop de doublons mal gérés, ajouter le champ `Obsolete__c` sur `NEILON__File__c` (cf ADR-014 picklist `Type_document__c`) avec trigger SF qui marque les anciens comme obsolètes quand un nouveau du même type arrive.

### Conséquences
- ➕ Cycle de vie explicite, lisible par tous (vendeur, comptable, dev)
- ➕ Re-déclenchement uniquement sur action vendeur explicite (pas sur chaque modif aléatoire de fichier) → évite des re-analyses inutiles
- ➕ Le statut est visible dans SF → le vendeur sait où en est son dossier (transparence)
- ➕ Compatible avec le dashboard comptable (filtre `Statut_dossier__c = en_attente_validation_comptable`)
- ➖ Demande à Salesforce admin : 1 picklist + 1 trigger + 1 bouton UI vendeur (effort moyen, 1-2 jours admin SF)
- ➖ Discipline vendeur requise : il doit penser à cliquer "J'ai corrigé" après ses modifs. Si oublié, le dossier reste bloqué en `en_anomalie_a_corriger`. À atténuer par : reminder mail au bout de N jours, ou trigger auto sur modif fichier.

### Indicateurs à monitorer (Phase 6)
- Taux de dossiers bloqués > 7 jours en `en_anomalie_a_corriger` (= vendeur a oublié de cliquer)
- Nombre moyen de boucles par dossier (combien de fois un même dossier repasse en analyse)
- Coût IA moyen / dossier (cible < 0,50 €) — si trop, optimiser dédup ou passer en cible

---

## ADR-016 — Dashboard comptable Streamlit pour la validation humaine

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
ADR-013 impose une validation humaine systématique par le comptable HESS avant tout envoi mail vendeur. Avec 1000 dossiers/jour, gérer cette validation par email serait ingérable (boîte saturée, oublis, pas de vue d'ensemble, pas de capacité d'édition fine des anomalies). Il faut un **outil dédié**.

### Décision
Créer un **dashboard comptable web** où le comptable peut :
1. Voir la liste des dossiers en attente de validation, triés par priorité (date, marque, indice de confiance)
2. Ouvrir un dossier → preview des PDFs + verdict IA + liste d'anomalies
3. **Éditer la liste d'anomalies** : ajouter (faux négatif IA), retirer (faux positif IA), modifier
4. **Inverser le verdict** si le comptable n'est pas d'accord avec l'IA
5. Cliquer "Valider et envoyer" → déclenche le mail vendeur avec la version **finale** + update SF
6. Voir les stats : combien analysés, validés, en attente, taux d'accord IA/comptable

### Stack — Streamlit
- Python 3.12 (cohérent avec l'API)
- Connexion lecture/écriture à Supabase (table `analyses`, `validations`)
- Appelle l'API `POST /validation/{analyse_id}` pour déclencher l'envoi mail
- Auth : magic link email HESS (via Supabase Auth) ou simple token partagé pour démarrer

### Alternatives écartées
- **React/Next.js** : 5-10× plus long à développer pour un MVP interne (1-5 utilisateurs). À envisager si on doit l'ouvrir à des externes plus tard.
- **Emails de validation avec liens cliquables** : ne scale pas, pas d'édition fine, pas de stats
- **Salesforce custom UI** : nécessite Apex/LWC, expertise SF lourde, lock-in fort

### Structure technique

```
app_dashboard/
├── streamlit_app.py        # entrée principale
├── pages/
│   ├── 1_📥_En_attente.py   # liste des dossiers à valider
│   ├── 2_✅_Valides.py       # historique récent
│   └── 3_📊_Stats.py        # métriques IA/comptable
├── services/
│   ├── supabase.py          # client Supabase (lit analyses, update validations)
│   └── api.py               # appelle /validation/{id} de l'API
└── components/
    ├── dossier_card.py      # composant carte dossier
    ├── anomalies_editor.py  # éditeur de liste d'anomalies
    └── pdf_viewer.py        # preview PDF embarqué
```

### Nouvelle table Supabase

```sql
CREATE TABLE validations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analyse_id          UUID NOT NULL REFERENCES analyses(id),
    opportunity_id      TEXT NOT NULL,
    statut              TEXT NOT NULL,        -- 'en_attente' | 'validee_conforme' | 'validee_non_conforme'
    decision_comptable  TEXT,                 -- 'confirme_ia' | 'inverse_ia' | 'modifie'
    anomalies_finales   JSONB NOT NULL,       -- liste finale après édition
    anomalies_ajoutees  JSONB,                -- ce que l'IA avait raté
    anomalies_retirees  JSONB,                -- faux positifs IA
    comptable_email     TEXT,
    notes               TEXT,
    cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    valide_le           TIMESTAMPTZ
);
```

### Endpoints API à ajouter (Phase 3+)

- `GET /validation/en-attente` : liste paginée des analyses sans validation
- `GET /validation/{analyse_id}` : détail d'un dossier (analyse + PDFs URLs)
- `POST /validation/{analyse_id}` : valider, payload `{decision, anomalies_finales, notes}` → déclenche mail vendeur via n8n

### Conséquences
- ➕ UX comptable bien meilleure que des emails
- ➕ Métriques d'amélioration IA en temps réel (taux d'accord IA/comptable par marque/concession)
- ➕ Dataset doré généré automatiquement (anomalies ajoutées/retirées) → input direct pour itérer sur les prompts
- ➕ Hébergement simple sur Render (à côté de l'API) ou Streamlit Cloud
- ➖ Code supplémentaire à maintenir (~500-1000 lignes)
- ➖ Auth à gérer proprement (magic link Supabase Auth — gratuit en plan free)

### Roadmap impact
Nouvelle **Phase 5b — Dashboard comptable** entre Phase 5 (intégration n8n) et Phase 6 (roll-out). Estimation 3-5 jours de dev pour un MVP fonctionnel. À détailler dans `phase-5b-dashboard-comptable.md` quand on s'y attaquera.

---

## ADR-017 — Règles de refus d'office : bypass IA + bypass comptable, mail vendeur direct

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Certains dossiers ne nécessitent **aucune analyse IA** ni **aucune validation comptable** parce que la règle qui les rend invalides est binaire, claire et incontestable. Exemple : un dossier rattaché à la concession "Siège" HESS est une erreur de saisie pure — pas la peine de gaspiller des tokens IA ni de surcharger le comptable.

Faire passer ces cas dans le pipeline standard (IA → dashboard comptable → mail) gaspille :
- Des tokens Gemini (~0,02-0,05 € par dossier)
- Du temps comptable (1-2 min par dossier × volume)
- De la latence (le vendeur attend des heures pour une info évidente)

### Décision
Créer un mécanisme de **refus d'office** : vérification déterministe en amont de l'appel Gemini. Si une règle matche, on court-circuite tout le pipeline :

```
Verdict = "refus_office"
Mail vendeur direct (CC comptable pour audit)
Update SF Statut_dossier__c = en_anomalie_a_corriger
FIN
```

### Implémentation

**Phase 3 (API)** :
- Module `app/core/refus_office.py` avec fonction `check_refus_office(opportunity) -> RefusOffice | None`
- Appelé **avant** l'appel Gemini dans `/analyze`
- Si match → retourner directement le verdict sans appeler Gemini
- Type Pydantic dédié `RefusOffice` : `{ regle: str, libelle: str, message_vendeur: str }`

**Phase 5 (n8n + template mail)** :
- Workflow secondaire `Leasing_v2_refus_office` : envoie un mail spécifique au vendeur (template HTML `mail_refus_office.html`)
- CC comptable pour audit (pas de validation requise, info uniquement)
- Update SF en une seule transaction

### Règles de refus d'office (à coder en Phase 3, liste évolutive)

| Code | Condition | Message vendeur |
|------|-----------|-----------------|
| `R001_siege` | `Concession_du_proprietaire__c == 'Siège'` | "Le dossier doit être rattaché à un point de vente, pas au Siège HESS. Merci de modifier la concession dans Salesforce et de redéposer." |
| `R002_avant_dispositif` (à valider) | `CloseDate < 2025-09-30` | "Le dispositif Leasing Social n'est entré en vigueur que le 30/09/2025." |
| _futures règles_ | _à acter au fur et à mesure_ | _selon le cas_ |

La liste est volontairement **conservatrice** : on n'ajoute une règle de refus d'office que si elle est **100% binaire** et **incontestable**. Tout cas ambigu doit rester dans le flow IA + comptable pour ne pas créer de faux négatifs définitifs.

### Conséquences
- ➕ Économie de tokens IA et de temps comptable sur les cas évidents
- ➕ Réactivité maximale pour le vendeur (mail immédiat)
- ➕ Code testable unitairement (pas d'IA dans la boucle)
- ➖ Risque si on ajoute une règle trop large et qu'elle bloque des dossiers valides — d'où la conservatisme
- ➖ Le comptable ne valide pas, donc moins de boucle d'apprentissage sur ces cas — acceptable car les règles sont triviales

### Lien avec ADR-013 (validation humaine systématique)
Exception explicite : ADR-013 impose la validation comptable pour les verdicts `conforme` et `non_conforme`. Le verdict `refus_office` est **un 5e statut séparé**, hors du périmètre de la validation comptable. Le comptable est informé en CC mais n'a rien à valider.

### Statuts SF à supporter (extension de ADR-015)
Ajout d'une transition possible dans le cycle de vie :
- `nouveau` / `corrige_a_reverifier` → API détecte refus d'office → `en_anomalie_a_corriger` directement (skip `en_attente_validation_comptable`)

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
