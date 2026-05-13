"""Phase 0 — Seed initial du mapping concessions dans Supabase.

Source : workflow n8n v1 (`N8N.txt`, node "Mapping concession").
Idempotent : utilise UPSERT sur `nom_salesforce`.

Usage:
    python scripts/seed_concessions.py
    python scripts/seed_concessions.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from supabase import Client, create_client

from app.config import get_settings

# Extrait du node "Mapping concession" du workflow n8n v1.
# Format : nom_salesforce -> email_conformite.
CONCESSION_MAPPING: dict[str, str] = {
    "Fiat Belfort": "fiatbelfortconformite@hessautomobile.com",
    "Fiat Besançon": "fiatbesanconconformite@hessautomobile.com",
    "Fiat Bischheim": "fiatbischheimconformite@hessautomobile.com",
    "Fiat Colmar": "fiatcolmarconformite@hessautomobile.com",
    "Fiat Dijon": "fiatdijonconformite@hessautomobile.com",
    "Jeep Dijon": "fiatdijonconformite@hessautomobile.com",  # mutualisé Fiat Dijon
    "Fiat Mulhouse": "fiatmulhouseconformite@hessautomobile.com",
    "Hyundai Besançon": "hyundaibesanconconformite@hessautomobile.com",
    "Hyundai Châlons": "hyundaichalonsconformite@hessautomobile.com",
    "Hyundai Colmar": "hyundaicolmarconformite@hessautomobile.com",
    "Hyundai Mulhouse": "hyundaimulhouseconformite@hessautomobile.com",
    "Hyundai Reims": "hyundaireimsconformite@hessautomobile.com",
    "Hyundai Strasbourg": "hyundaistrasbourgconformite@hessautomobile.com",
    "Hyundai Epernay": "hyundaiepernayconformite@hessautomobile.com",
    "Nissan Belfort": "nissanbelfortconformite@hessautomobile.com",
    "Nissan Colmar": "nissancolmarconformite@hessautomobile.com",
    "Nissan Dijon": "nissandijonconformite@hessautomobile.com",
    "Nissan Haguenau": "nissanhaguenauconformite@hessautomobile.com",
    "Nissan Metz": "nissanmetzconformite@hessautomobile.com",
    "Nissan Montbéliard": "nissanmontbeliardconformite@hessautomobile.com",
    "Nissan Mulhouse": "nissanmulhouseconformite@hessautomobile.com",
    "Nissan Nancy": "nissannancyconformite@hessautomobile.com",
    "Nissan Strasbourg": "nissanstrasbourgconformite@hessautomobile.com",
    "Nissan Thionville": "nissanthionvilleconformite@hessautomobile.com",
    "Opel Belfort": "opelbelfortconformite@hessautomobile.com",
    "Opel Besançon": "opelbesanconconformite@hessautomobile.com",
    "Opel Charleville": "opelcharlevilleconformite@hessautomobile.com",
    "Opel Dijon": "opeldijonconformite@hessautomobile.com",
    "Opel Metz": "opelmetzconformite@hessautomobile.com",
    "Opel Nancy": "opelnancyconformite@hessautomobile.com",
    "Opel Thionville": "opelthionvilleconformite@hessautomobile.com",
    "Opel Bar-le-Duc": "opelbarleducconformite@hessautomobile.com",
    "Opel Verdun": "opelverdunconformite@hessautomobile.com",
    "Opel Saint-Dizier": "opelsaintdizierconformite@hessautomobile.com",
    "Peugeot Charleville": "peugeotcharlevilleconformite@hessautomobile.com",
    "Peugeot Hirson": "peugeothirsonconformite@hessautomobile.com",
    "Peugeot Reims": "peugeotreimsconformite@hessautomobile.com",
    "Peugeot Sedan": "peugeotsedanconformite@hessautomobile.com",
    "Renault Belfort": "renaultbelfortconformite@hessautomobile.com",
    "Renault Colmar": "renaultcolmarconformite@hessautomobile.com",
    "Renault Haguenau": "renaulthaguenauconformite@hessautomobile.com",
    "Renault Montbéliard": "renaultmontbeliardconformite@hessautomobile.com",
    "Renault Mulhouse": "renaultmulhouseconformite@hessautomobile.com",
    "Renault Saint-Louis": "renaultsaint-louisconformite@hessautomobile.com",
    "Renault Saverne": "renaultsaverneconformite@hessautomobile.com",
    "Renault Sélestat": "renaultselestatconformite@hessautomobile.com",
    "Renault Strasbourg Hautepierre": "renaultstrasbourghautepierreconformite@hessautomobile.com",
    "Renault Strasbourg Illkirch": "renaultstrasbourgillkirchconformite@hessautomobile.com",
    "Renault Wissembourg": "renaultwissembourgconformite@hessautomobile.com",
    "Toyota Belfort": "toyotabelfortconformite@hessautomobile.com",
    "Toyota Besançon": "toyotabesanconconformite@hessautomobile.com",
    "Toyota Forbach": "toyotaforbachconformite@hessautomobile.com",
    "Toyota Longwy": "toyotalongwyconformite@hessautomobile.com",
    "Toyota Metz": "toyotametzconformite@hessautomobile.com",
    "Toyota Montbéliard": "toyotamontbeliardconformite@hessautomobile.com",
    "Toyota Sarreguemines": "toyotasarregueminesconformite@hessautomobile.com",
    "Toyota Thionville": "toyotathionvilleconformite@hessautomobile.com",
    "Toyota Bar-le-Duc": "toyotabarleducconformite@hessautomobile.com",
    "Toyota Verdun": "toyotaverdunconformite@hessautomobile.com",
    "Toyota Saint-Dizier": "toyotasaintdizierconformite@hessautomobile.com",
}


def normalize_marque(nom_salesforce: str) -> str:
    """Extrait la marque depuis le nom de concession ("Fiat Belfort" -> "fiat")."""
    return nom_salesforce.split(" ")[0].lower()


def normalize_ville(nom_salesforce: str) -> str:
    """Extrait la ville depuis le nom de concession ("Fiat Belfort" -> "Belfort")."""
    parts = nom_salesforce.split(" ", 1)
    return parts[1] if len(parts) > 1 else ""


def build_rows() -> list[dict[str, object]]:
    """Construit les lignes à insérer."""
    now_iso = datetime.now(UTC).isoformat()
    rows: list[dict[str, object]] = []
    for nom_sf, email in sorted(CONCESSION_MAPPING.items()):
        rows.append(
            {
                "nom_salesforce": nom_sf,
                "marque": normalize_marque(nom_sf),
                "ville": normalize_ville(nom_sf),
                "email_conformite": email,
                "emails_cc": [],
                "actif": True,
                "modifie_le": now_iso,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'écrit pas en base, affiche seulement ce qui serait inséré.",
    )
    args = parser.parse_args()

    rows = build_rows()
    print(f"Concessions à seeder : {len(rows)}")

    marques = sorted({row["marque"] for row in rows})
    print(f"Marques couvertes ({len(marques)}) : {', '.join(str(m) for m in marques)}")
    print("⚠️  Le périmètre HESS réel est 10-15 marques. Mapping n8n v1 couvre 8 marques.")
    print("   Les marques manquantes seront identifiées en Phase 1 via SF.\n")

    if args.dry_run:
        print("--dry-run actif, pas d'écriture Supabase. Aperçu :")
        for row in rows[:5]:
            print(f"  {row}")
        print(f"  ... et {len(rows) - 5} autres")
        return 0

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        print("ERREUR : SUPABASE_URL et SUPABASE_KEY doivent être définis dans .env")
        return 1

    client: Client = create_client(settings.supabase_url, settings.supabase_key)
    response = client.table("concessions").upsert(rows, on_conflict="nom_salesforce").execute()

    print(f"✅ {len(response.data)} concessions upsertées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
