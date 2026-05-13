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

## ADR-015 — Cycle de vie SF via les champs existants (pas de nouveau champ)

**Date** : 2026-05-13 (rév. 2026-05-13 — découverte que SF fait déjà le job nativement)
**Statut** : Acceptée

### Contexte
Quand l'IA + le comptable concluent que le dossier est en anomalie, le mail au vendeur dit "modifier le dossier dans Salesforce". Le vendeur ne crée pas un nouveau dossier, il modifie le dossier existant.

Initialement (révision précédente de cet ADR), on prévoyait de créer un champ custom `Statut_dossier__c` + un trigger SF + un bouton UI vendeur. **Inutile** : SF gère déjà tout nativement.

### Découverte clé (2026-05-13)
- `Tech_Dossier_verifier__c` (champ existant, booléen) **se décoche automatiquement** par SF dès qu'un fichier `NEILON__File__c` est modifié sur l'opportunité. Mécanisme natif, pas de trigger custom à écrire.
- `Conformite_du_dossier__c` (champ existant, picklist) contient déjà toutes les valeurs nécessaires : `- Aucun -` / `Client inéligible` / `Document absent ou à corriger` / `Bon pour livraison` / `Dossier conforme après la livraison`.

### Décision

**1. On utilise les 2 champs SF existants** (pas de demande admin SF) :

| Champ | Notre rôle |
|-------|------------|
| `Tech_Dossier_verifier__c` | Signal "à (re-)analyser" — lu par n8n, repassé à TRUE par l'API après validation comptable |
| `Conformite_du_dossier__c` | Verdict final visible côté SF |

**2. Mapping verdict interne ↔ valeur SF picklist** :

| Notre `Verdict.statut` | Valeur écrite dans `Conformite_du_dossier__c` |
|------------------------|------------------------------------------------|
| `refus_office` | `Client inéligible` |
| `non_conforme` | `Document absent ou à corriger` |
| `conforme` | `Bon pour livraison` |
| `erreur_technique` | Inchangé (re-tente prochain cycle) |
| `aucun_doc` | Inchangé + alerte Sentry |

**3. SOQL de production** :

```sql
SELECT ...
FROM Opportunity
WHERE Leasing_electrique__c = TRUE
  AND Tech_Dossier_verifier__c = FALSE
  AND StageName = '4- Gagné'
  AND Conformite_du_dossier__c NOT IN (
    'Bon pour livraison',
    'Dossier conforme après la livraison',
    'Client inéligible'
  )
  AND Concession_du_proprietaire__c != 'Siège'
```

**4. Déduplication côté API** : analyser tous les `NEILON__File__c` reçus, mais au moment du verdict, ne garder que le plus récent par `type_document` détecté par Gemini (basé sur `CreatedDate`).

### Flow complet

```
Vendeur upload dossier sur SF
   ↓
SF : Tech_Dossier_verifier__c = FALSE (par défaut)
   ↓
n8n cron : SOQL → trouve l'opp
   ↓
n8n → API /analyze
   ↓
API : refus_office.check → si match : Conformite_du_dossier__c = 'Client inéligible' + mail vendeur direct, FIN
   ↓
Sinon : Gemini → verification.py → écrit verdict en base Supabase (statut_validation = en_attente)
   ↓
Comptable ouvre le dashboard → édite anomalies → clique "Valider"
   ↓
Dashboard → API /validation :
   - écrit dans Supabase (table validations)
   - patch SF : Conformite_du_dossier__c = (valeur mappée) + Tech_Dossier_verifier__c = TRUE
   - déclenche webhook n8n → mail vendeur final
   ↓
Si vendeur corrige un fichier dans SF :
   ↓
SF (natif) : Tech_Dossier_verifier__c = FALSE
   ↓
Retour au début (n8n picke au prochain cycle)
```

### Ce qui change par rapport à la version précédente de cet ADR
- ❌ Plus de création du champ `Statut_dossier__c` à demander à Renzo
- ❌ Plus de trigger SF custom à écrire (le décochage auto de `Tech_Dossier_verifier__c` est natif)
- ❌ Plus de bouton "J'ai corrigé" dans l'UI vendeur SF
- ✅ On n'utilise QUE les champs SF existants

### Conséquences
- ➕ Zéro travail Salesforce admin requis (énorme gain de temps)
- ➕ Comportement natif SF = plus fiable qu'un trigger custom
- ➕ Aucune discipline vendeur requise (pas de bouton à ne pas oublier)
- ➕ Le vendeur voit `Conformite_du_dossier__c` directement dans l'UI Opportunity → transparence
- ➖ Moins de granularité que prévue initialement (on ne distingue plus `en_cours_analyse` vs `en_attente_validation_comptable` côté SF — cette info reste interne à Supabase)
- ➖ La granularité interne (statut Supabase) est invisible côté SF — acceptable, le comptable utilise le dashboard pour ça

### Indicateurs à monitorer (Phase 6)
- Taux de dossiers bloqués > 7 jours en `Conformite_du_dossier__c = 'Document absent ou à corriger'` (= vendeur a oublié de corriger)
- Nombre moyen de boucles par dossier
- Coût IA moyen / dossier (cible < 0,50 €)

---

## ADR-016 — Dashboard comptable Streamlit pour la validation humaine

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
ADR-013 impose une validation humaine systématique par le comptable HESS avant tout envoi mail vendeur. Avec 1000 dossiers/jour, gérer cette validation par email serait ingérable (boîte saturée, oublis, pas de vue d'ensemble, pas de capacité d'édition fine des anomalies). Il faut un **outil dédié**.

### Décision
Créer un **dashboard comptable web qui sert de back-office unique** pour Axel — il n'a idéalement jamais besoin d'ouvrir Salesforce directement. Le dashboard pilote tout via l'API FastAPI qui synchronise SF en arrière-plan.

**Fonctions** :
1. Voir la liste des dossiers en attente de validation, triés par priorité (date, marque, indice de confiance)
2. Ouvrir un dossier → preview des PDFs + verdict IA + liste d'anomalies + détails opp SF
3. **Éditer la liste d'anomalies** : ajouter (faux négatif IA), retirer (faux positif IA), modifier
4. **Inverser le verdict** si le comptable n'est pas d'accord avec l'IA
5. Cliquer "Valider et envoyer" → déclenche le mail vendeur avec la version **finale** + update SF
6. **Changer `StageName`** depuis le dashboard (4-Gagné → 5-Perdu, etc.) — synchronisé SF
7. **Override manuel `Conformite_du_dossier__c`** (cas d'urgence ou correction) — synchronisé SF
8. **Forcer une ré-analyse** d'un dossier (décoche `Tech_Dossier_verifier__c`)
9. Voir les stats : combien analysés, validés, en attente, taux d'accord IA/comptable, par marque, par jour

**Principe architectural** : Streamlit n'appelle **jamais** Salesforce directement. Toute écriture SF passe par l'API FastAPI (centralisation logique métier, cohérence, audit).

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

## ADR-018 — Défense en profondeur face aux changements de format documents

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Les marques (Fiat, Renault, etc.) et leurs filiales financières (Stellantis Finance, RCI, Hyundai Capital, etc.) peuvent **changer le format de leurs documents** sans prévenir HESS : refonte BDC, nouveau template contrat, nouveau libellé "Prix TTC", etc.

Risques associés :
- Le prompt spécifique de la marque ne reconnaît plus certains champs → indice de confiance chute
- L'IA peut halluciner (deviner) ou rater des anomalies → faux positifs / faux négatifs en cascade
- Sans filet, des centaines de dossiers partent en erreur en production

### Décision
Empiler **5 niveaux de filet** indépendants pour garantir qu'aucun dossier ne sorte erroné même en cas de changement de format complet.

### Les 5 niveaux

#### Niveau 1 — Cascade de prompts (cf ADR-005)

Résolution automatique : `(marque, concession)` → `(marque, NULL)` → `('default', NULL)`. Si le prompt spécifique d'une concession est obsolète, on tombe sur le prompt marque générique. Si lui aussi est obsolète, on tombe sur le `default`. Aucun dossier ne plante par manque de prompt.

#### Niveau 2 — Validation Pydantic stricte (cf ADR-009)

Si Gemini renvoie du JSON cassé ou avec des champs hallucinés :
- Retry 2x avec backoff exponentiel (1s, 4s)
- Si toujours invalide → verdict `erreur_technique` (jamais "conforme" par défaut)
- Logging structuré du prompt + réponse brute pour debug

#### Niveau 3 — Indice de confiance auto-calculé

Si Gemini extrait peu de champs (parce que le libellé a changé), l'indice de confiance baisse mécaniquement. Le dashboard comptable (ADR-016) trie les dossiers à faible confiance **en haut de la queue** pour qu'ils soient revus en priorité.

#### Niveau 4 — Détection de drift par marque/concession (à coder Phase 6)

Surveillance automatique des métriques par marque :
- Taux d'accord IA / comptable (cf ADR-016)
- Taux d'extraction réussie des champs critiques (`prix_ttc`, `loyer_hors_options`, `nature_bdc`)
- Indice de confiance moyen

Si une marque chute brutalement (ex: -27 points en 7 jours), **alerte Sentry** : "drift Fiat détecté sur BDC, le prompt v1 doit être révisé". Toi/Renzo écrivez alors un prompt v2, vous le pushez en base Supabase (toggle `actif = TRUE`), pas besoin de redéployer le code.

#### Niveau 5 — Filet ultime : validation comptable systématique (cf ADR-013)

**Aucun mail vendeur ne part sans clic comptable**, peu importe le verdict IA. Donc même si l'IA est complètement dans les choux pendant 2 jours à cause d'un nouveau format Fiat :
- ❌ Aucun vendeur ne reçoit de mail erroné
- ✅ Le comptable corrige manuellement les anomalies / inverse les verdicts dans le dashboard
- ✅ Il signale qu'il faut adapter le prompt
- ✅ La donnée de correction alimente automatiquement le dataset d'amélioration

### Scénario nominal de gestion d'un changement de format

```
J : Fiat sort un nouveau BDC v3 chez Fiat Mulhouse
J+1 : 3 dossiers Fiat Mulhouse arrivent
  ↓
  API analyse via le prompt (fiat, NULL, extraction_bdc) — fallback marque
  ↓
  Indice de confiance Fiat Mulhouse chute : 92% → 60%
  ↓
  Dashboard comptable : ces dossiers remontent en haut de la queue
  ↓
  Comptable valide manuellement, indique "Mulhouse a un nouveau BDC"
  ↓
  Sentry alerte automatiquement après 5 dossiers similaires
  ↓
J+3 : Toi/Renzo regardez le nouveau BDC Mulhouse
J+4 : Écrivez un nouveau prompt (fiat, Fiat Mulhouse, extraction_bdc) v1
J+5 : UPSERT dans Supabase, actif=TRUE
       → la cascade prend immédiatement le nouveau prompt
       → pas de redéploiement, pas d'interruption
J+6 : Précision Fiat Mulhouse remonte à 95%+
```

### Constat stabilisateur

Sur les ~15 types de documents d'un dossier :
- **~8 sont des formulaires Cerfa nationaux** (attestations LVEREB-1085, géoportail, avis impôts) → standardisés par l'ASP, ne changent que si l'État réforme
- **Seuls le BDC et le contrat de location** varient par marque/financier

Donc même un changement de format BDC ne touche que ~15-20% des documents d'un dossier. Le reste continue de marcher normalement, et la précision globale du verdict ne s'effondre pas brutalement.

### Conséquences
- ➕ Aucun "single point of failure" — chaque niveau peut tomber sans cascade
- ➕ Évolution gracieuse : le dégradement de qualité est visible (indice de confiance, taux d'accord) avant d'impacter les vendeurs
- ➕ Mise à jour de prompts à chaud, sans redéploiement (Supabase = source de vérité technique)
- ➕ Le comptable n'est jamais bypassé → crédibilité préservée
- ➖ Charge comptable temporairement élevée en cas de drift (plus de dossiers à revoir manuellement)
- ➖ Latence légèrement augmentée si le drift n'est pas détecté rapidement

### À monitorer en Phase 6
- Taux d'accord IA / comptable hebdomadaire par marque (cible >85% en stabilisation)
- Indice de confiance moyen par marque (alerte si >10 points de chute en 7 jours)
- Délai moyen entre "détection drift" et "prompt v2 actif"

---

## ADR-019 — Authentification du dashboard : Google OAuth + whitelist d'emails

**Date** : 2026-05-13
**Statut** : Acceptée

### Contexte
Le dashboard Streamlit (ADR-016) donne accès à des données ultra-sensibles (RFR, CNI, IBAN, etc.) et permet de modifier des dossiers Salesforce. Il faut une auth solide et fermée.

### Décision

**1. Streamlit utilise Google OAuth 2.0 (OpenID Connect)** via `st.login()` natif (Streamlit ≥1.42).

**2. Whitelist d'emails préautorisés** dans variable d'env `DASHBOARD_ALLOWED_EMAILS` (CSV). Pas d'inscription, pas d'auto-provisioning. Tout email non-listé est rejeté avec un message clair.

**3. L'API FastAPI reste protégée par `API_TOKEN`** (déjà en place). Le dashboard envoie ce token à chaque appel. L'API trace l'utilisateur via un header `X-User-Email: <email>` que Streamlit injecte depuis le token Google.

### Emails initialement autorisés
- `axelsaphir@hessautomobile.com` (comptable)
- `tiffanydellmann@hessautomobile.com` (admin/dev)

À ajouter dans `DASHBOARD_ALLOWED_EMAILS` au moment du déploiement Phase 5b.

### Flux d'authentification

```
1. Axel ouvre https://dashboard.hess.../
2. Streamlit : "Connectez-vous avec Google"
3. Redirection Google OAuth → Axel s'authentifie sur son compte HESS
4. Google renvoie un id_token à Streamlit avec email + nom
5. Streamlit vérifie : email ∈ DASHBOARD_ALLOWED_EMAILS ?
   - Non → écran "Accès refusé, contactez l'administrateur"
   - Oui → session ouverte
6. À chaque appel API :
   Authorization: Bearer <API_TOKEN>
   X-User-Email: axelsaphir@hessautomobile.com
7. L'API trace l'email dans logs + table validations (audit)
```

### Pré-requis Google Cloud (Phase 5b)
- Projet Google Cloud (réutiliser un existant HESS si possible)
- Activer OAuth 2.0 Client ID (type Web application)
- Configurer le redirect URI vers le domaine du dashboard
- Récupérer `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` → `.env`

### Conséquences
- ➕ Sécurité forte : impossibilité de créer un compte, pas de mot de passe à voler
- ➕ Cohérent avec l'IT HESS si Google Workspace est utilisé
- ➕ Audit : email réel dans tous les logs et toutes les validations
- ➕ Révocation simple : retirer l'email de la whitelist
- ➖ Dépendance Google (mais HESS utilise déjà Gmail donc OK)
- ➖ Phase 5b ne peut pas avancer tant que les credentials Google Cloud ne sont pas en place

### Notes
- L'API n'utilise pas elle-même Google OAuth — elle valide juste le token partagé `API_TOKEN`. L'authentification utilisateur est entièrement côté Streamlit.
- Pour les appels n8n → API (workflow auto), n8n utilise le même `API_TOKEN` mais avec un header `X-User-Email: system@hessautomobile.com` pour distinguer les actions automatiques.

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
