"""Valeurs de référence ASP 2025 — règles métier.

Source : `glossaire.md` (qui consolide N8N v1 + PDF amélioration v2 + retours utilisateur).

⚠️ Ces valeurs peuvent évoluer si l'ASP réforme le dispositif. À terme, elles
seront chargées depuis une table Supabase `parametres_asp` avec date d'effet,
mais pour le MVP elles vivent ici en constantes Python.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# Éligibilité client
RFR_PAR_PART_MAX: int = 16_300

# Véhicule / aide
AIDE_RATIO_MAX_TTC: Decimal = Decimal("0.27")  # 27 % du prix TTC, jamais HT
AIDE_PLAFOND_EUR: int = 7_000
LOYER_MAX_HORS_OPTION: int = 200  # €/mois, strictement < 200
DUREE_MIN_MOIS: int = 36
KM_MIN_PAR_AN: int = 12_000
DATE_DEBUT_DISPOSITIF: date = date(2025, 9, 30)
DELAI_BDC_LIVRAISON_MAX_MOIS: int = 6

# Justificatif domicile
JUSTIF_DOMICILE_MAX_MOIS: int = 3

# Géoportail / distance
GEOPORTAIL_MODE_REQUIS: str = "Plus court"
DISTANCE_GEOPORTAIL_OBLIGATOIRE_KM: int = 15  # si distance < 15 km → géoportail requis
DISTANCE_SURVEILLANCE_MIN_KM: Decimal = Decimal("15.01")  # zone surveillance 15.01-18
DISTANCE_SURVEILLANCE_MAX_KM: int = 18
DISTANCE_EXCESSIVE_KM: int = 100  # > 100 km = alerte non bloquante

# BDC — frais et mentions
# Liste des libellés de frais reconnus comme autorisés (insensible à la casse).
# Toute frais hors de cette liste = anomalie bloquante.
FRAIS_AUTORISES_BDC: list[str] = [
    "mise à la route",
    "certificats",
    "frais d'envoi",
    "taxes",
    "immatriculation",
    "carte grise",
    "pack livraison",
    "frais de préparation",
    "frais de transport",
]

MENTIONS_INTERDITES_BDC: list[str] = ["bonus écologique"]

# Justif domicile interdits (factures non éligibles ASP)
JUSTIF_DOMICILE_TYPES_INTERDITS: list[str] = [
    "facture mobile",
    "facture téléphone mobile",
    "facture telephonie mobile",
]
