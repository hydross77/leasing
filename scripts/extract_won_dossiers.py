"""Phase 1 — Extraction des dossiers Leasing Social gagnés depuis Salesforce.

Lit les opportunités `Closed Won` + `Leasing_electrique__c = TRUE` sur 12 mois glissants,
télécharge les fichiers `NEILON__File__c` associés et les chiffre localement (Fernet).
Idempotent : un dossier déjà téléchargé est skip.

Source de vérité : Salesforce. Stockage local = analyse Phase 1 uniquement, purgé après Phase 2.
Voir ADR-004 (exception RGPD), `phase-1-extraction-dataset.md` pour le détail.

Usage:
    python scripts/extract_won_dossiers.py
    python scripts/extract_won_dossiers.py --limit 20
    python scripts/extract_won_dossiers.py --marque renault
    python scripts/extract_won_dossiers.py --metadata-only
    python scripts/extract_won_dossiers.py --report
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

from app.config import get_settings
from app.utils.logging import get_logger, setup_logging

log = get_logger("phase1.extract")


DATASET_ROOT = Path("dataset")
SOQL_OPPORTUNITIES = """
SELECT
    Id,
    Name,
    StageName,
    CloseDate,
    LastModifiedDate,
    Concession_du_proprietaire__c,
    Leasing_electrique__c,
    Conformite_du_dossier__c,
    Description
FROM Opportunity
WHERE
    Leasing_electrique__c = TRUE
    AND StageName = 'Closed Won'
    AND CloseDate = LAST_N_MONTHS:12
ORDER BY CloseDate DESC
"""

SOQL_FILES_TEMPLATE = """
SELECT
    Id,
    Name,
    CreatedDate,
    NEILON__Opportunity__c,
    NEILON__File_Presigned_URL__c
FROM NEILON__File__c
WHERE NEILON__Opportunity__c = '{opp_id}'
ORDER BY CreatedDate DESC
"""


def safe_slug(value: str) -> str:
    """Slugifie un nom pour utilisation en chemin de fichier (Windows safe)."""
    if not value:
        return "inconnu"
    forbidden = '<>:"/\\|?*'
    cleaned = "".join("_" if c in forbidden else c for c in value).strip()
    return cleaned or "inconnu"


def normalize_marque(concession: str | None) -> str:
    """Extrait la marque depuis `Concession_du_proprietaire__c`.

    Ex: "Fiat Belfort" -> "fiat", "Renault Strasbourg Hautepierre" -> "renault".
    """
    if not concession:
        return "inconnu"
    return concession.strip().split(" ")[0].lower()


def get_fernet(key: str) -> Fernet:
    """Construit un objet Fernet depuis la clé settings."""
    if not key:
        raise ValueError(
            "DATASET_ENCRYPTION_KEY manquant. Générer avec : "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, InvalidToken) as exc:
        raise ValueError(f"Clé Fernet invalide : {exc}") from exc


def connect_salesforce() -> Salesforce:
    """Authentification Salesforce via username/password/security token."""
    settings = get_settings()
    if not settings.salesforce_username or not settings.salesforce_password:
        raise ValueError("Identifiants Salesforce manquants dans .env")

    log.info("salesforce_connect", domain=settings.salesforce_domain)
    return Salesforce(
        username=settings.salesforce_username,
        password=settings.salesforce_password,
        security_token=settings.salesforce_token,
        domain=settings.salesforce_domain,
    )


def fetch_opportunities(
    sf: Salesforce,
    marque_filter: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Récupère toutes les opportunités gagnées Leasing électrique."""
    log.info("soql_opportunities_start")
    query = SOQL_OPPORTUNITIES
    if limit:
        query = query.replace("ORDER BY CloseDate DESC", f"ORDER BY CloseDate DESC LIMIT {limit}")

    try:
        result = sf.query_all(query)
    except SalesforceError as exc:
        log.error("soql_opportunities_failed", error=str(exc))
        raise

    records: list[dict[str, Any]] = result["records"]
    log.info("soql_opportunities_done", total=len(records))

    if marque_filter:
        before = len(records)
        records = [
            r
            for r in records
            if normalize_marque(r.get("Concession_du_proprietaire__c")) == marque_filter.lower()
        ]
        log.info("filter_marque_applied", marque=marque_filter, before=before, after=len(records))

    return records


def fetch_files_for_opp(sf: Salesforce, opp_id: str) -> list[dict[str, Any]]:
    """Liste les fichiers NEILON__File__c d'une opportunité."""
    try:
        result = sf.query_all(SOQL_FILES_TEMPLATE.format(opp_id=opp_id))
    except SalesforceError as exc:
        log.warning("soql_files_failed", opportunity_id=opp_id, error=str(exc))
        return []
    return result["records"]  # type: ignore[no-any-return]


def download_and_encrypt(
    url: str,
    target_path: Path,
    fernet: Fernet,
    client: httpx.Client,
    max_retries: int = 3,
) -> int | None:
    """Télécharge un fichier depuis URL et l'écrit chiffré sur disque.

    Retourne la taille en bytes du fichier original (avant chiffrement), ou None si échec.
    Idempotent : skip si target_path existe déjà.
    """
    if target_path.exists():
        log.debug("file_skip_exists", path=str(target_path))
        return target_path.stat().st_size

    for attempt in range(1, max_retries + 1):
        try:
            response = client.get(url, follow_redirects=True, timeout=60.0)
            response.raise_for_status()
            content = response.content
            size = len(content)
            encrypted = fernet.encrypt(content)
            target_path.write_bytes(encrypted)
            return size
        except httpx.HTTPError as exc:
            if attempt < max_retries:
                wait = 2**attempt
                log.warning("download_retry", attempt=attempt, wait_s=wait, error=str(exc))
                time.sleep(wait)
            else:
                log.error("download_failed", url=url[:80], error=str(exc))
                return None
    return None


def process_opportunity(
    sf: Salesforce,
    opp: dict[str, Any],
    fernet: Fernet,
    http_client: httpx.Client,
    metadata_only: bool,
) -> dict[str, Any] | None:
    """Traite une opportunité : récupère ses fichiers, les télécharge chiffrés, écrit manifest."""
    opp_id = opp["Id"]
    opp_name = opp.get("Name", "")
    concession = opp.get("Concession_du_proprietaire__c") or "inconnu"
    marque = normalize_marque(concession)

    target_dir = (
        DATASET_ROOT / "dossiers" / safe_slug(marque) / safe_slug(concession) / safe_slug(opp_id)
    )
    manifest_path = target_dir / "manifest.json"

    if manifest_path.exists() and not metadata_only:
        log.debug("opp_skip_already_processed", opportunity_id=opp_id)
        return json.loads(manifest_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    target_dir.mkdir(parents=True, exist_ok=True)

    files = fetch_files_for_opp(sf, opp_id)
    files_meta: list[dict[str, Any]] = []

    for f in files:
        original_name = f.get("Name") or f.get("Id") or "unknown"
        url = f.get("NEILON__File_Presigned_URL__c")
        encrypted_name = f"{safe_slug(original_name)}.enc"
        size: int | None = None

        if not metadata_only and url:
            size = download_and_encrypt(url, target_dir / encrypted_name, fernet, http_client)

        files_meta.append(
            {
                "id": f.get("Id"),
                "original_name": original_name,
                "size_bytes": size,
                "encrypted_path": encrypted_name if not metadata_only else None,
                "created_date": f.get("CreatedDate"),
            }
        )

    manifest = {
        "opportunity_id": opp_id,
        "opportunity_name": opp_name,
        "marque": marque,
        "concession": concession,
        "close_date": opp.get("CloseDate"),
        "last_modified_date": opp.get("LastModifiedDate"),
        "conformite_du_dossier": opp.get("Conformite_du_dossier__c"),
        "leasing_electrique": opp.get("Leasing_electrique__c"),
        "files": files_meta,
        "extracted_at": datetime.now(UTC).isoformat(),
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    log.info(
        "opp_processed",
        opportunity_id=opp_id,
        marque=marque,
        concession=concession,
        nb_files=len(files_meta),
    )
    return manifest


def write_aggregated_metadata(manifests: list[dict[str, Any]]) -> None:
    """Écrit `dataset/metadata.jsonl` agrégé."""
    DATASET_ROOT.mkdir(exist_ok=True)
    metadata_path = DATASET_ROOT / "metadata.jsonl"
    with metadata_path.open("w", encoding="utf-8") as fh:
        for m in manifests:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    log.info("metadata_written", path=str(metadata_path), count=len(manifests))


def write_stats_report(manifests: list[dict[str, Any]], known_concessions: set[str]) -> None:
    """Génère `dataset-stats.md` avec les agrégats."""
    by_marque: Counter[str] = Counter()
    by_pair: defaultdict[tuple[str, str], int] = defaultdict(int)
    file_sizes_by_pair: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    file_name_patterns: Counter[str] = Counter()
    files_per_dossier: list[int] = []
    unknown_concessions: set[str] = set()

    for m in manifests:
        marque = m["marque"]
        concession = m["concession"]
        by_marque[marque] += 1
        by_pair[(marque, concession)] += 1
        if concession not in known_concessions and concession != "inconnu":
            unknown_concessions.add(concession)
        files_per_dossier.append(len(m["files"]))
        for f in m["files"]:
            name = f.get("original_name", "").lower()
            if name.startswith("scan_"):
                file_name_patterns["Scan_*"] += 1
            elif name.startswith("scanner@"):
                file_name_patterns["scanner@*"] += 1
            elif "bdc" in name or "bon" in name:
                file_name_patterns["BDC*"] += 1
            elif "contrat" in name:
                file_name_patterns["Contrat*"] += 1
            elif "cni" in name or "identit" in name:
                file_name_patterns["CNI/Identité*"] += 1
            else:
                file_name_patterns["autre"] += 1
            if size := f.get("size_bytes"):
                file_sizes_by_pair[(marque, concession)].append(size)

    lines: list[str] = []
    lines.append("# Statistiques dataset Phase 1\n")
    lines.append(f"Généré : {datetime.now(UTC).isoformat()}\n")
    lines.append(f"## Total\n\n- Dossiers extraits : **{len(manifests)}**\n")
    if files_per_dossier:
        lines.append(
            f"- Nb fichiers/dossier : min={min(files_per_dossier)}, "
            f"max={max(files_per_dossier)}, "
            f"moy={sum(files_per_dossier) / len(files_per_dossier):.1f}\n"
        )

    lines.append("\n## Par marque\n\n| Marque | Nb dossiers |\n|--------|-------------|\n")
    for marque, count in by_marque.most_common():
        lines.append(f"| {marque} | {count} |\n")

    lines.append("\n## Par couple (marque, concession)\n\n")
    lines.append("| Marque | Concession | Nb dossiers |\n|--------|-----------|------------|\n")
    for (marque, concession), count in sorted(
        by_pair.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(f"| {marque} | {concession} | {count} |\n")

    if unknown_concessions:
        lines.append("\n## ⚠️ Concessions hors mapping n8n v1\n\n")
        for c in sorted(unknown_concessions):
            lines.append(f"- {c}\n")
        lines.append(
            "\nÀ ajouter à la table `concessions` de Supabase et au mapping email.\n"
        )

    lines.append("\n## Patterns de nommage des fichiers\n\n")
    lines.append("| Pattern | Nb |\n|---------|----|\n")
    for pattern, count in file_name_patterns.most_common():
        lines.append(f"| {pattern} | {count} |\n")

    report_path = Path("dataset-stats.md")
    report_path.write_text("".join(lines), encoding="utf-8")
    log.info("stats_report_written", path=str(report_path))
    print(f"\n📊 Rapport : {report_path.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Limiter le nb d'opportunités")
    parser.add_argument("--marque", type=str, default=None, help="Filtrer une marque")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Ne télécharge pas les PDFs, juste les métadonnées",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Génère le rapport stats à partir des manifests déjà extraits, sans re-fetch SF",
    )
    args = parser.parse_args()

    setup_logging(get_settings().log_level)

    # Mode --report : on lit juste les manifests existants
    if args.report:
        manifests: list[dict[str, Any]] = []
        for manifest_path in DATASET_ROOT.glob("dossiers/**/manifest.json"):
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        log.info("report_mode", manifests_found=len(manifests))
        from scripts.seed_concessions import CONCESSION_MAPPING

        write_stats_report(manifests, set(CONCESSION_MAPPING.keys()))
        return 0

    settings = get_settings()
    fernet = get_fernet(settings.dataset_encryption_key)

    sf = connect_salesforce()
    opportunities = fetch_opportunities(sf, marque_filter=args.marque, limit=args.limit)

    if not opportunities:
        log.warning("no_opportunities_found")
        return 0

    manifests = []
    with httpx.Client() as http_client:
        for i, opp in enumerate(opportunities, 1):
            try:
                manifest = process_opportunity(
                    sf, opp, fernet, http_client, args.metadata_only
                )
                if manifest:
                    manifests.append(manifest)
                if i % 20 == 0:
                    log.info("progress", processed=i, total=len(opportunities))
            except Exception as exc:  # noqa: BLE001 — on log et on continue
                log.error(
                    "opp_processing_failed",
                    opportunity_id=opp.get("Id"),
                    error=str(exc),
                )

    write_aggregated_metadata(manifests)

    from scripts.seed_concessions import CONCESSION_MAPPING

    write_stats_report(manifests, set(CONCESSION_MAPPING.keys()))

    log.info("extraction_done", total=len(manifests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
