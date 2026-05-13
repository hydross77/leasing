---
name: reference_n8n_v1
description: Référence vers le workflow n8n v1 existant (N8N.txt) — source de vérité de la logique métier actuelle à porter en v2
metadata:
  type: reference
---

Le fichier `N8N.txt` à la racine du projet contient le **workflow n8n complet du système v1** (l'existant en production). C'est la source de référence pour la logique métier à porter en v2.

**Éléments clés à y retrouver** :

- **SOQL traitement** (node `Information_opportunite`) : `SELECT Id, Name, TECH_ConcessionName__c, TECH_OwnerName__c, LastModifiedDate, Concession_du_proprietaire__c FROM Opportunity WHERE Leasing_electrique__c = TRUE AND Tech_Dossier_verifier__c = FALSE LIMIT 20`
- **SOQL fichiers** (node `Perform a query1`) : `SELECT Id, Name, CreatedDate, CreatedById, NEILON__Opportunity__c, NEILON__File_Presigned_URL__c FROM NEILON__File__c WHERE NEILON__Opportunity__c = '{{id}}' ORDER BY CreatedDate DESC`
- **Prompt extraction Gemini 2.5 Pro** (node `Analyze document`) : prompt très long avec ~25 champs `donnees_extraites` (zone_ecriture_client, premier_loyer_hors_option, geoportail, piece_identite, etc.)
- **Prompt vérification GPT-5-mini** (node `Vérificateur conformité`) : encode toutes les règles ASP 2025, contient les anomalies critiques. **Bug à corriger : liste actuellement le RIB comme obligatoire** alors que le PDF v2 indique qu'il ne l'est plus.
- **Prompt génération mail GPT-4** (node `Génère mail`) : à migrer vers GPT-5-mini en v2 (cf ADR-007).
- **Mapping concessions** (node `Mapping concession`) : ~58 concessions vers email_diffusion@hessautomobile.com. À transférer dans la table Supabase `concessions`.
- **Génération HTML mail** (node `Code1`) : template HTML inline charte HESS (navy `#2E3152` + accent doré `#C9A978`).
- **Champs Salesforce mis à jour** : `Tech_Dossier_verifier__c`, `Conformite_du_dossier__c`, `Date_livraison_definitive__c`, `Description`.
- **Schedule trigger** : toutes les 4 secondes (`0 */4 * * * *`) — agressif, à revoir.
- **Destinataires mail interne** : renzodisantolo@hessautomobile.com (TO), aurelienpottier + alexandreschott (CC).

**Why:** L'utilisatrice a transmis ce fichier comme base historique à exploiter pour la refonte v2. Le workflow contient tout ce qui tourne actuellement en prod, y compris les anomalies décrites dans [[project_anomalies_v1]].

**How to apply:**
- Phase 1 : extraire le mapping concessions pour seeder Supabase
- Phase 2 : utiliser les prompts existants comme baseline puis les éclater par marque
- Phase 3 : porter les règles ASP du prompt vérificateur dans `verification.py` Python pur (cf ADR-007 note)
- Phase 5 : reproduire les emails (TO/CC, charte HTML)
