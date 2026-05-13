"""Phase 1 — Analyse exploratoire des dossiers extraits par Gemini.

⚠️ PROMPT VOLONTAIREMENT OUVERT : on ne fixe PAS le schéma de production ici. L'objectif
est de découvrir les patterns par marque/concession pour alimenter l'écriture des prompts
Phase 2 (rétro-ingénierie). Aucun prompt de production n'est écrit en Phase 1.

Lit les manifests générés par `extract_won_dossiers.py`, déchiffre les PDFs en RAM,
les envoie à Gemini 2.5 Pro avec un prompt court et ouvert, et écrit les réponses
brutes dans `dataset/exploration_qualitative.jsonl`.

Usage:
    python scripts/analyze_dataset.py --sample-per-pair 10
    python scripts/analyze_dataset.py --marque renault --sample-per-pair 20
    python scripts/analyze_dataset.py --no-llm    # juste les stats, sans appel Gemini
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import google.generativeai as genai
from cryptography.fernet import Fernet

from app.config import get_settings
from app.utils.logging import get_logger, setup_logging

log = get_logger("phase1.analyze")


DATASET_ROOT = Path("dataset")
EXPLORATION_OUTPUT = DATASET_ROOT / "exploration_qualitative.jsonl"
DEFAULT_MODEL = "gemini-2.5-pro"


# ⚠️ Ce prompt est délibérément OUVERT. On découvre, on ne contraint pas encore.
EXPLORATION_PROMPT = """Tu es un assistant d'analyse documentaire. On te transmet un document issu d'un dossier client de leasing automobile (HESS Automobile, France).

Tâches :
1. Identifie le type de document parmi : bon de commande (BDC), contrat de location, carte d'identité, permis de conduire, justificatif de domicile, avis d'imposition, attestation gros rouleur, attestation respect engagements, attestation respect loyers, carte grise, photo véhicule (VIN/arrière/macaron), géoportail, RIB, fiche restitution véhicule, autre.

2. Décris en 5-10 lignes les éléments caractéristiques de ce document : libellés, sections, mentions, mise en page, logo / marque visible, présence de signatures, présence de cases à cocher.

3. Si c'est un BDC ou un contrat de location :
   - liste TOUS les libellés exacts utilisés pour : prix HT, prix TTC, loyer mensuel, loyer hors options, durée, kilométrage, frais (mise à la route, immatriculation, pack livraison, certificats, etc.), nature du document (achat / location)
   - identifie clairement la case ou le champ qui distingue "achat" de "location" (case à cocher, dropdown, mention texte)

4. Note tout élément qui te surprend ou qui semble propre à cette marque / concession (mention atypique, logo de filiale financière, formulaire spécifique, mention "Bonus écologique" interdite, etc.).

Réponds STRICTEMENT en JSON valide, sans texte autour, dans ce format :
{
  "type_document": "...",
  "description": "...",
  "marque_logo_detectee": "...",
  "libelles_cles": {
    "prix_ttc": "...",
    "loyer_hors_options": "...",
    "nature": "..."
  },
  "cases_cochees_detectees": ["..."],
  "particularites": ["..."]
}

Si tu ne peux pas analyser le document, retourne :
{"type_document": "illisible", "description": "raison", ...}
"""


def get_fernet(key: str) -> Fernet:
    if not key:
        raise ValueError("DATASET_ENCRYPTION_KEY manquant dans .env")
    return Fernet(key.encode())


def load_manifests(marque_filter: str | None = None) -> list[dict[str, Any]]:
    """Charge les manifests des dossiers extraits."""
    manifests: list[dict[str, Any]] = []
    for manifest_path in DATASET_ROOT.glob("dossiers/**/manifest.json"):
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        if marque_filter and m["marque"] != marque_filter.lower():
            continue
        m["_path"] = str(manifest_path.parent)
        manifests.append(m)
    return manifests


def sample_by_pair(
    manifests: list[dict[str, Any]],
    sample_per_pair: int,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Échantillonne `sample_per_pair` dossiers par couple (marque, concession)."""
    rng = random.Random(seed)
    by_pair: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for m in manifests:
        by_pair[(m["marque"], m["concession"])].append(m)

    sampled: list[dict[str, Any]] = []
    for pair, items in by_pair.items():
        if len(items) <= sample_per_pair:
            sampled.extend(items)
        else:
            sampled.extend(rng.sample(items, sample_per_pair))
        log.debug(
            "sampled_pair",
            marque=pair[0],
            concession=pair[1],
            available=len(items),
            taken=min(len(items), sample_per_pair),
        )
    return sampled


def decrypt_pdf(encrypted_path: Path, fernet: Fernet) -> bytes:
    """Déchiffre un PDF en RAM."""
    return fernet.decrypt(encrypted_path.read_bytes())


def analyze_pdf_with_gemini(
    model: genai.GenerativeModel,
    pdf_bytes: bytes,
    max_retries: int = 2,
) -> dict[str, Any] | None:
    """Envoie un PDF à Gemini avec le prompt d'exploration. Parse JSON ou None."""
    for attempt in range(1, max_retries + 1):
        try:
            response = model.generate_content(
                [
                    EXPLORATION_PROMPT,
                    {"mime_type": "application/pdf", "data": pdf_bytes},
                ],
                request_options={"timeout": 90},
            )
            text = response.text.strip()
            # Tolérance : supprimer un éventuel fence ```json
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            log.warning(
                "gemini_json_invalid",
                attempt=attempt,
                error=str(exc),
                preview=text[:200] if "text" in locals() else "",
            )
        except Exception as exc:  # noqa: BLE001 — Gemini wrap ses erreurs
            log.warning("gemini_call_failed", attempt=attempt, error=str(exc))
            if attempt < max_retries:
                time.sleep(2**attempt)
    return None


def process_manifest(
    manifest: dict[str, Any],
    model: genai.GenerativeModel | None,
    fernet: Fernet,
    output_fh: Any,
) -> int:
    """Analyse tous les fichiers d'un dossier. Retourne le nb d'analyses réussies."""
    manifest_dir = Path(manifest["_path"])
    success = 0

    for file_meta in manifest["files"]:
        encrypted_path = manifest_dir / (file_meta.get("encrypted_path") or "")
        if not encrypted_path.exists():
            log.debug("file_missing", path=str(encrypted_path))
            continue

        result_entry = {
            "opportunity_id": manifest["opportunity_id"],
            "marque": manifest["marque"],
            "concession": manifest["concession"],
            "file_name": file_meta.get("original_name"),
            "file_size_bytes": file_meta.get("size_bytes"),
        }

        if model is None:
            result_entry["analysis"] = None
            result_entry["mode"] = "no-llm"
        else:
            try:
                pdf_bytes = decrypt_pdf(encrypted_path, fernet)
            except Exception as exc:  # noqa: BLE001
                log.error("decrypt_failed", path=str(encrypted_path), error=str(exc))
                continue

            analysis = analyze_pdf_with_gemini(model, pdf_bytes)
            result_entry["analysis"] = analysis
            result_entry["mode"] = "llm"
            if analysis:
                success += 1

        output_fh.write(json.dumps(result_entry, ensure_ascii=False) + "\n")
        output_fh.flush()

    return success


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-per-pair",
        type=int,
        default=10,
        help="Nb de dossiers échantillonnés par couple (marque, concession)",
    )
    parser.add_argument("--marque", type=str, default=None, help="Filtrer une marque")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Pas d'appel Gemini, génère juste l'index des dossiers échantillonnés",
    )
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL, help="Modèle Gemini à utiliser"
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    manifests = load_manifests(marque_filter=args.marque)
    log.info("manifests_loaded", total=len(manifests))

    if not manifests:
        log.error("no_manifests_found", hint="Lancer d'abord extract_won_dossiers.py")
        return 1

    sampled = sample_by_pair(manifests, args.sample_per_pair)
    log.info("sampled", count=len(sampled))

    fernet = get_fernet(settings.dataset_encryption_key)

    model: genai.GenerativeModel | None = None
    if not args.no_llm:
        if not settings.gemini_api_key:
            log.error("gemini_api_key_missing")
            return 1
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(args.model)
        log.info("gemini_model_ready", model=args.model)

    DATASET_ROOT.mkdir(exist_ok=True)
    total_success = 0
    with EXPLORATION_OUTPUT.open("a", encoding="utf-8") as fh:
        for i, manifest in enumerate(sampled, 1):
            try:
                success = process_manifest(manifest, model, fernet, fh)
                total_success += success
                if i % 10 == 0:
                    log.info(
                        "progress", processed=i, total=len(sampled), success=total_success
                    )
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "manifest_analysis_failed",
                    opportunity_id=manifest.get("opportunity_id"),
                    error=str(exc),
                )

    log.info(
        "analysis_done",
        manifests_processed=len(sampled),
        files_analyzed_success=total_success,
        output=str(EXPLORATION_OUTPUT),
    )
    print(f"\n✅ Sortie : {EXPLORATION_OUTPUT.resolve()}")
    print("Étape suivante : rédiger `dossier-formats-par-marque.md` à partir de ce JSONL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
