---
name: project_human_in_the_loop
description: Décision produit clé — validation humaine obligatoire avant tout mail concession sur les non_conformes
metadata:
  type: project
---

Décision du 2026-05-13 (cf ADR-013) : **aucun mail "non conforme" ne part chez la concession sans validation humaine préalable** par l'équipe HESS (Renzo / Aurélien / Alexandre).

Motivation : le système v1 envoie en parallèle le mail interne ET le mail concession sur `non_conforme`. Quand l'IA se trompe (10 cas listés dans le PDF d'amélioration), le vendeur reçoit une fausse alerte → crédibilité détruite.

**Why:** L'utilisatrice (2026-05-13) a soulevé : "si l'ia se trompe c'est chaud on est plus credible". C'est aussi la conséquence directe des faux positifs documentés dans [[project_anomalies_v1]].

**How to apply:**
- Tous les mails "non conforme" du flow v2 partent en TO Renzo + CC Aurélien/Alexandre, jamais en TO concession directement.
- Conforme : mail concession direct (faible risque).
- Non conforme : Statut_validation_humaine__c = en_attente, mail interne avec liens Approuver/Rejeter, mail concession différé.
- Erreur technique / aucun doc : pas de mail concession.
- À terme (post-backtest stable >95%), possibilité de bascule auto pour indice de confiance ≥ 90% — décision séparée le moment venu.

Implémentation côté Phase 5 (n8n + nouvel endpoint API). Ne pas l'oublier en concevant l'archi mails de l'API.
