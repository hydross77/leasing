---
name: project_destinataires_mails
description: Destinataires des mails v2 — ni Renzo, ni Aurélien, ni Alexandre. Comptable unique = axelsaphir@
metadata:
  type: project
---

**Correction importante 2026-05-13** : contrairement à ce que laissait penser le workflow n8n v1 (qui mettait Renzo en TO + Aurélien/Alexandre en CC) et à ce que j'avais initialement supposé, **aucun de ces trois n'est destinataire des mails v2**.

**Destinataires v2 (à respecter dans tout le code et toutes les docs)** :

| Rôle | Email | Quand |
|------|-------|-------|
| **Comptable HESS** | `axelsaphir@hessautomobile.com` | TO sur tous les mails en MAIL_MODE=prod |
| **Vendeur** | Depuis Salesforce (`Opportunity.Owner.Email`, via payload n8n) | TO sur mail vendeur en prod (refus d'office + après validation comptable) |
| **Concession (diffusion)** | Depuis table Supabase `concessions.email_conformite` | CC quand applicable en prod |
| **Tiffany** (test/dev) | `tiffanydellmann@hessautomobile.com` | TO unique en MAIL_MODE=test, écrase tout le reste |

**Why:** L'utilisatrice a confirmé le 2026-05-13 : "ni aurelien, ni renzo, ni alexandre personne. moi la dev+test tiffanydellmann@..., le comptable axelsaphir@..., les vendeurs via salesforce".

**How to apply:**
- `app/config.py` : `mail_comptable: str = "axelsaphir@hessautomobile.com"` (un seul, pas de liste)
- `.env` / `.env.example` : `MAIL_COMPTABLE=axelsaphir@hessautomobile.com` (pas de CC)
- ADR-013 (validation comptable), ADR-016 (dashboard), ADR-017 (refus d'office) : retirer toute mention de Renzo/Aurélien/Alexandre comme destinataires de mails (ils restent contacts projet dans CLAUDE.md).
- Toutes les références "Renzo + Aurélien + Alexandre" dans les memories antérieures doivent être corrigées.
- En MAIL_MODE=test, le bandeau d'audit doit montrer **les vrais destinataires prod** (axel + vendeur SF + concession) pour que Tiffany vérifie qu'ils seraient corrects.
