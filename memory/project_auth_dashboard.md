---
name: project_auth_dashboard
description: Authentification dashboard — Google OAuth + whitelist d'emails, pas d'inscription (ADR-019)
metadata:
  type: project
---

Le dashboard Streamlit n'autorise **que** Google OAuth + whitelist d'emails préautorisés. Aucune inscription possible, aucun mot de passe local. Tout email hors whitelist est rejeté avec écran "Contactez l'administrateur".

**Décision (ADR-019)** :
- Streamlit `st.login()` natif (≥1.42) avec provider Google OpenID Connect
- Variable `DASHBOARD_ALLOWED_EMAILS` (CSV) dans `.env`
- API protégée par `API_TOKEN` partagé (déjà en place) + header `X-User-Email` pour audit

**Emails initialement autorisés** (à confirmer au déploiement) :
- axelsaphir@hessautomobile.com (comptable)
- tiffanydellmann@hessautomobile.com (admin/dev)

**Why:** L'utilisatrice (2026-05-13) a précisé "connexion qu'avec google pour le dashboard et des emails bien defini, pas d'inscription". Sécurité forte sur un back-office qui manipule des données RGPD ultra-sensibles.

**How to apply:**
- Phase 5b : implémenter le `st.login()` Google + check whitelist
- Phase 5b : créer les credentials Google Cloud OAuth (Web application)
- API : ajouter le middleware d'extraction `X-User-Email` pour audit
- Logs : tous les logs `event=validation_*` doivent contenir l'email réel de l'utilisateur
- Audit : la table `validations` Supabase a déjà `comptable_email` — l'utiliser systématiquement
- Pour les appels n8n auto → API, utiliser `X-User-Email: system@hessautomobile.com` (réservé pour distinguer auto vs manuel)
