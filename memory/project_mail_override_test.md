---
name: project_mail_override_test
description: En phase de test, tous les mails sortants sont redirigés vers tiffanydellmann@hessautomobile.com
metadata:
  type: project
---

En dev/test/staging, **aucun mail ne doit partir vers les vrais destinataires** (concessions, équipe). Tous les mails sortants (interne, concession, relance post-livraison, alerte 6 mois) sont redirigés vers `tiffanydellmann@hessautomobile.com`.

**Mécanisme** : variable d'environnement `MAIL_RECIPIENT_OVERRIDE` (settings `app.config.Settings.mail_recipient_override`).
- En **prod** : vide → comportement normal.
- En **dev / staging / phase de test** : `tiffanydellmann@hessautomobile.com` → toutes les TO/CC/BCC sont remplacées par cette adresse, et le sujet doit être préfixé par `[TEST]` ou similaire pour identifier qu'il s'agit d'un test.

**Why:** Tiffany pilote les phases de test et veut concentrer la réception pour vérifier les mails sans risquer d'envoyer des fausses alertes aux concessions ou de polluer la boîte interne. Demandé le 2026-05-13.

**How to apply:**
- L'API qui retourne `mail.destinataire_principal` / `mail.cc` doit appliquer cet override **avant** de construire la réponse.
- Côté n8n (Phase 5) : si l'API a déjà remplacé les destinataires, n8n n'a rien à faire. Sinon n8n applique l'override à son niveau (Set node avant le Gmail node).
- Préfixer le sujet par `[TEST]` quand l'override est actif (utile pour Tiffany).
- Ne **jamais** désactiver l'override silencieusement en prod : si `ENV=prod`, l'override doit être ignoré ou refuser de démarrer si présent.
