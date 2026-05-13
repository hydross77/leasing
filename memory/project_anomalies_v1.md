---
name: project_anomalies_v1
description: Anomalies du système v1 (n8n actuel) à éviter dans la refonte — recensées dans le PDF "Amélioration Leasing Social"
metadata:
  type: project
---

Le système n8n actuel génère des **faux positifs** (alertes alors que conforme) sur plusieurs catégories. À éviter absolument lors de la conception des prompts v2 (Phase 2) et des règles métier (Phase 3).

**Faux positifs avérés en production v1** :

1. **RFR / nombre de parts** sur avis d'imposition : alerte remonte même quand le calcul est conforme. Cas : Renault Mulhouse / Zakaria MAJDOUNE (18 624 € / 2 parts = 9 312 €/part conforme mais alerté).
2. **Pièces d'identité** : CNI/passeport valide mais "absence de date" ou "non vérifiable" remonté. Cas : Renault Saverne / MEHMET SEN.
3. **BDC prix TTC** : prix TTC bien présent mais IA dit "manquant". Cas : Hyundai Strasbourg / SCHUBNEL.
4. **Calcul aide vs prix** : IA calcule l'aide en % du **HT** au lieu du **TTC**. Cas : Renault Illkirch / MOUNIR BOUKKAZA.
5. **Frais administratifs vs frais autorisés** : IA confond frais d'immatriculation, pack livraison, mise à la route (autorisés) avec "frais administratifs interdits". Cas : Renault Colmar / Stéphane Siettler ; Peugeot Reims / FELLAH.
6. **Justificatif de domicile "daté du futur"** : faux positif sur des docs conformes. Cas : Renault Sélestat / JM Hein.
7. **Délai 6 mois + contradiction de dates** : alerte erronée alors que BDC 30/09/2025 et livraison décembre 2025 sont cohérents. Cas : Renault Mulhouse / Camille GAULT.
8. **Cases cochées (achat vs location)** : IA détecte "achat comptant" alors que c'est "location" qui est coché. Cas : Hyundai Strasbourg / Mustafa UCA ; Peugeot Reims / DE GUILLEBON.
9. **Loyer avec options vs hors options** : IA prend le loyer **avec** options au lieu du loyer hors options. Cas : Fiat Mulhouse / Mohamed RIAD (268,14 € avec options vs 196,96 € hors options conforme).

**Why:** Ces 9 patterns doivent être traités en priorité dans les prompts et dans la couche de vérification, sinon la confiance utilisateur reste cassée comme en v1.

**How to apply:**
- Phase 2 (prompts) : chaque prompt extraction doit forcer Gemini à distinguer **explicitement** loyer hors options / avec options, frais autorisés / interdits, case cochée location / achat, RFR brut + nb_parts + calcul attendu.
- Phase 3 (verification.py) : règle aide ≤ 27 % TTC doit **toujours** utiliser le prix TTC, jamais HT. Les frais autorisés sont : mise à la route, certificats, frais d'envoi, taxes, immatriculation, pack livraison, frais de préparation. Tout autre frais = anomalie.
- Backtest Phase 4 : utiliser ces 9 cas comme test set explicite (non-régression).
