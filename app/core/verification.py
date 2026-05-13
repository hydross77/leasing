"""Règles de vérification ASP 2025 (Phase 3).

Chaque règle est une fonction pure qui prend une partie du dossier et retourne
`Anomalie | None`. Pas d'IA ici : Python déterministe, testable unitairement,
100% reproductible.

Architecture :
    - `verifier_*` : une fonction par règle
    - `verifier_dossier(dossier) -> Verdict` : orchestre toutes les règles

Référence : `glossaire.md` (règles), `verification_rules.py` (seuils).

⚠️ Sécurité par défaut : en cas d'incertitude, on lève une anomalie plutôt que
de laisser passer. Aucun dossier n'est conforme par défaut.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.core.verification_rules import (
    AIDE_PLAFOND_EUR,
    AIDE_RATIO_MAX_TTC,
    DATE_DEBUT_DISPOSITIF,
    DELAI_BDC_LIVRAISON_MAX_MOIS,
    DISTANCE_EXCESSIVE_KM,
    DISTANCE_GEOPORTAIL_OBLIGATOIRE_KM,
    DISTANCE_SURVEILLANCE_MAX_KM,
    DISTANCE_SURVEILLANCE_MIN_KM,
    DUREE_MIN_MOIS,
    FRAIS_AUTORISES_BDC,
    GEOPORTAIL_MODE_REQUIS,
    JUSTIF_DOMICILE_MAX_MOIS,
    JUSTIF_DOMICILE_TYPES_INTERDITS,
    KM_MIN_PAR_AN,
    LOYER_MAX_HORS_OPTION,
    RFR_PAR_PART_MAX,
)
from app.models.anomalie import Anomalie
from app.models.document import (
    AvisImposition,
    BonDeCommande,
    ContratLocation,
    DossierExtrait,
    Geoportail,
    JustificatifDomicile,
)
from app.models.verdict import Statut, Verdict

# ============================================================================
# Helpers
# ============================================================================


def _add_months(d: date, months: int) -> date:
    """Ajoute approximativement N mois à une date (30 jours/mois pour simplicité)."""
    return d + timedelta(days=30 * months)


# ============================================================================
# Règles éligibilité client
# ============================================================================


def verifier_rfr_part(avis: AvisImposition | None) -> Anomalie | None:
    """A001 — RFR / nombre de parts ≤ 16 300 €."""
    if avis is None or avis.revenu_fiscal_reference is None or avis.nombre_parts is None:
        return None  # Anomalie « document manquant » remontée ailleurs
    if avis.nombre_parts == 0:
        return Anomalie(
            code="A001_rfr_part",
            libelle="Nombre de parts à 0 sur l'avis d'imposition",
            detail="Division par zéro impossible — vérifier l'avis d'imposition",
            severite="bloquante",
            document_concerne="avis_imposition",
        )
    rfr_par_part = avis.revenu_fiscal_reference / avis.nombre_parts
    if rfr_par_part > RFR_PAR_PART_MAX:
        return Anomalie(
            code="A001_rfr_part",
            libelle="Revenu fiscal de référence par part trop élevé",
            detail=(
                f"{avis.revenu_fiscal_reference} € / {avis.nombre_parts} parts = "
                f"{rfr_par_part:.2f} €/part, seuil ASP {RFR_PAR_PART_MAX} €"
            ),
            severite="bloquante",
            document_concerne="avis_imposition",
        )
    return None


# ============================================================================
# Règles véhicule / aide (BDC)
# ============================================================================


def verifier_aide_ratio_ttc(bdc: BonDeCommande | None) -> Anomalie | None:
    """A005 — Aide ≤ 27 % du prix TTC (jamais HT — bug v1).

    Correction PDF amélioration v2 §A5 : calcul sur TTC uniquement.
    """
    if bdc is None or bdc.prix_ttc is None or bdc.montant_aide_etat is None:
        return None
    if bdc.prix_ttc <= 0:
        return Anomalie(
            code="A005_aide_27_ttc",
            libelle="Prix TTC invalide sur le bon de commande",
            detail=f"Prix TTC = {bdc.prix_ttc} €",
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    ratio = bdc.montant_aide_etat / bdc.prix_ttc
    if ratio > AIDE_RATIO_MAX_TTC:
        seuil_eur = bdc.prix_ttc * AIDE_RATIO_MAX_TTC
        return Anomalie(
            code="A005_aide_27_ttc",
            libelle="Aide de l'État supérieure à 27 % du prix TTC",
            detail=(
                f"Aide {bdc.montant_aide_etat} € sur prix TTC {bdc.prix_ttc} € "
                f"= {ratio:.2%} (seuil 27 % soit {seuil_eur:.2f} €)"
            ),
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    return None


def verifier_aide_plafond(bdc: BonDeCommande | None) -> Anomalie | None:
    """A006 — Aide ≤ 7 000 € en absolu."""
    if bdc is None or bdc.montant_aide_etat is None:
        return None
    if bdc.montant_aide_etat > AIDE_PLAFOND_EUR:
        return Anomalie(
            code="A006_aide_plafond",
            libelle=f"Aide supérieure au plafond de {AIDE_PLAFOND_EUR} €",
            detail=f"Aide constatée : {bdc.montant_aide_etat} €",
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    return None


def verifier_bonus_ecologique_interdit(bdc: BonDeCommande | None) -> Anomalie | None:
    """A007 — Mention « Bonus écologique » interdite sur BDC."""
    if bdc is None:
        return None
    if bdc.mention_bonus_ecologique:
        return Anomalie(
            code="A007_bonus_ecologique",
            libelle="Mention « Bonus écologique » présente sur le bon de commande",
            detail="L'aide Leasing Social n'est pas cumulable avec le bonus écologique",
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    return None


def verifier_frais_autorises(bdc: BonDeCommande | None) -> Anomalie | None:
    """A008 — Tous les frais du BDC doivent être dans la liste autorisée.

    Correction PDF v2 §A6 : la liste inclut maintenant immatriculation, pack
    livraison, frais de préparation (faux positifs v1 corrigés).
    """
    if bdc is None or not bdc.libelles_frais:
        return None
    autorises_norm = [f.lower() for f in FRAIS_AUTORISES_BDC]
    frais_interdits = [
        f for f in bdc.libelles_frais
        if not any(autorise in f.lower() for autorise in autorises_norm)
    ]
    if frais_interdits:
        return Anomalie(
            code="A008_frais_interdits",
            libelle="Frais non autorisés détectés sur le bon de commande",
            detail=f"Frais interdits : {', '.join(frais_interdits)}",
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    return None


def verifier_delai_bdc_livraison(bdc: BonDeCommande | None) -> Anomalie | None:
    """A009 — Délai BDC → livraison ≤ 6 mois (nouveau, PDF v2)."""
    if bdc is None or bdc.date_signature is None or bdc.date_livraison_prevue is None:
        return None
    limite = _add_months(bdc.date_signature, DELAI_BDC_LIVRAISON_MAX_MOIS)
    if bdc.date_livraison_prevue > limite:
        return Anomalie(
            code="A009_delai_6_mois",
            libelle=f"Délai BDC → livraison supérieur à {DELAI_BDC_LIVRAISON_MAX_MOIS} mois",
            detail=(
                f"BDC signé le {bdc.date_signature.isoformat()}, "
                f"livraison prévue le {bdc.date_livraison_prevue.isoformat()}"
            ),
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    return None


def verifier_date_debut_dispositif(bdc: BonDeCommande | None) -> Anomalie | None:
    """A010 — BDC signé après le 30/09/2025 (date début dispositif)."""
    if bdc is None or bdc.date_signature is None:
        return None
    if bdc.date_signature < DATE_DEBUT_DISPOSITIF:
        return Anomalie(
            code="A010_avant_dispositif",
            libelle="Bon de commande signé avant l'entrée en vigueur du dispositif",
            detail=(
                f"BDC du {bdc.date_signature.isoformat()}, "
                f"dispositif depuis le {DATE_DEBUT_DISPOSITIF.isoformat()}"
            ),
            severite="bloquante",
            document_concerne="bon_de_commande",
        )
    return None


# ============================================================================
# Règles contrat de location
# ============================================================================


def verifier_loyer_hors_options(contrat: ContratLocation | None) -> Anomalie | None:
    """A011 — Loyer mensuel hors options < 200 €.

    Correction PDF v2 §A10 : utilise STRICTEMENT le loyer hors options, jamais
    le loyer avec options (bug v1 récurrent).
    """
    if contrat is None or contrat.loyer_mensuel_hors_options is None:
        return None
    if contrat.loyer_mensuel_hors_options >= LOYER_MAX_HORS_OPTION:
        return Anomalie(
            code="A011_loyer_max",
            libelle=f"Loyer mensuel hors options ≥ {LOYER_MAX_HORS_OPTION} €",
            detail=(
                f"Loyer hors options constaté : {contrat.loyer_mensuel_hors_options} €/mois "
                f"(plafond ASP < {LOYER_MAX_HORS_OPTION} €)"
            ),
            severite="bloquante",
            document_concerne="contrat_location",
        )
    return None


def verifier_duree_location(contrat: ContratLocation | None) -> Anomalie | None:
    """A012 — Durée de location ≥ 36 mois (3 ans)."""
    if contrat is None or contrat.duree_mois is None:
        return None
    if contrat.duree_mois < DUREE_MIN_MOIS:
        return Anomalie(
            code="A012_duree_location",
            libelle=f"Durée de location inférieure à {DUREE_MIN_MOIS} mois",
            detail=f"Durée constatée : {contrat.duree_mois} mois",
            severite="bloquante",
            document_concerne="contrat_location",
        )
    return None


def verifier_kilometrage(contrat: ContratLocation | None) -> Anomalie | None:
    """A013 — Kilométrage annuel ≥ 12 000 km."""
    if contrat is None or contrat.kilometrage_annuel is None:
        return None
    if contrat.kilometrage_annuel < KM_MIN_PAR_AN:
        return Anomalie(
            code="A013_kilometrage",
            libelle=f"Kilométrage annuel inférieur à {KM_MIN_PAR_AN} km",
            detail=f"Kilométrage constaté : {contrat.kilometrage_annuel} km/an",
            severite="bloquante",
            document_concerne="contrat_location",
        )
    return None


# ============================================================================
# Règles justificatif de domicile
# ============================================================================


def verifier_justificatif_domicile(
    justif: JustificatifDomicile | None,
    date_premier_loyer: date | None = None,
) -> Anomalie | None:
    """A020 — Justificatif domicile ≤ 3 mois ET pas de facture mobile.

    Si `date_premier_loyer` non fournie, on compare à `date.today()` (cas Phase 1 d'analyse).
    """
    if justif is None:
        return None
    # Règle 1 : pas de facture mobile
    if justif.est_facture_mobile is True:
        return Anomalie(
            code="A020_justif_mobile",
            libelle="Justificatif de domicile = facture de téléphone mobile (interdit ASP)",
            detail=f"Type détecté : {justif.type_justif}",
            severite="bloquante",
            document_concerne="justificatif_domicile",
        )
    if justif.type_justif and any(
        interdit in justif.type_justif.lower()
        for interdit in JUSTIF_DOMICILE_TYPES_INTERDITS
    ):
        return Anomalie(
            code="A020_justif_mobile",
            libelle="Justificatif de domicile non éligible (facture mobile)",
            detail=f"Type détecté : {justif.type_justif}",
            severite="bloquante",
            document_concerne="justificatif_domicile",
        )
    # Règle 2 : âge ≤ 3 mois
    if justif.date_document is None:
        return None
    reference = date_premier_loyer or date.today()
    limite = _add_months(justif.date_document, JUSTIF_DOMICILE_MAX_MOIS)
    if reference > limite:
        return Anomalie(
            code="A021_justif_anciennete",
            libelle=f"Justificatif de domicile vieux de plus de {JUSTIF_DOMICILE_MAX_MOIS} mois",
            detail=(
                f"Document du {justif.date_document.isoformat()}, "
                f"référence du {reference.isoformat()}"
            ),
            severite="bloquante",
            document_concerne="justificatif_domicile",
        )
    return None


# ============================================================================
# Règles géoportail / distance
# ============================================================================


def verifier_geoportail_mode(geo: Geoportail | None) -> Anomalie | None:
    """A030 — Géoportail en mode 'Plus court' obligatoire."""
    if geo is None or geo.mode_calcul is None:
        return None
    if geo.mode_calcul != GEOPORTAIL_MODE_REQUIS:
        return Anomalie(
            code="A030_geoportail_mode",
            libelle=f"Géoportail en mode « {geo.mode_calcul} »",
            detail=f"Seul le mode « {GEOPORTAIL_MODE_REQUIS} » est accepté par l'ASP",
            severite="bloquante",
            document_concerne="geoportail",
        )
    return None


def verifier_geoportail_distance(
    geo: Geoportail | None, dossier_a_geoportail: bool
) -> Anomalie | None:
    """A031 — Géoportail obligatoire si distance domicile-travail < 15 km.

    On lève une alerte non bloquante en zone de surveillance (15.01-18 km) et
    en distance excessive (> 100 km).
    """
    if geo is None or geo.distance_km is None:
        return None
    distance = geo.distance_km
    if distance < DISTANCE_GEOPORTAIL_OBLIGATOIRE_KM and not dossier_a_geoportail:
        return Anomalie(
            code="A031_geoportail_obligatoire",
            libelle=f"Géoportail obligatoire car distance < {DISTANCE_GEOPORTAIL_OBLIGATOIRE_KM} km",
            detail=f"Distance domicile-travail : {distance} km",
            severite="bloquante",
            document_concerne="geoportail",
        )
    if DISTANCE_SURVEILLANCE_MIN_KM <= distance <= DISTANCE_SURVEILLANCE_MAX_KM:
        return Anomalie(
            code="A032_zone_surveillance",
            libelle=f"Distance en zone de surveillance ASP ({distance} km)",
            detail=f"Plage {DISTANCE_SURVEILLANCE_MIN_KM} a {DISTANCE_SURVEILLANCE_MAX_KM} km",
            severite="alerte",
            document_concerne="geoportail",
        )
    if distance > DISTANCE_EXCESSIVE_KM:
        return Anomalie(
            code="A033_distance_excessive",
            libelle=f"Distance domicile-travail supérieure à {DISTANCE_EXCESSIVE_KM} km",
            detail=f"Distance constatée : {distance} km — à vérifier",
            severite="alerte",
            document_concerne="geoportail",
        )
    return None


# ============================================================================
# Orchestrateur
# ============================================================================

# Liste des règles à exécuter et leur fonction associée.
# L'ordre n'a pas d'importance fonctionnelle mais peut influer sur l'affichage.

REGLES_BDC = [
    verifier_aide_ratio_ttc,
    verifier_aide_plafond,
    verifier_bonus_ecologique_interdit,
    verifier_frais_autorises,
    verifier_delai_bdc_livraison,
    verifier_date_debut_dispositif,
]

REGLES_CONTRAT = [
    verifier_loyer_hors_options,
    verifier_duree_location,
    verifier_kilometrage,
]


def verifier_dossier(
    dossier: DossierExtrait,
    date_premier_loyer: date | None = None,
) -> Verdict:
    """Applique toutes les règles ASP 2025 sur un dossier extrait.

    Args:
        dossier: données extraites par Gemini, agrégées
        date_premier_loyer: utilisée pour les règles d'ancienneté (justif domicile)

    Returns:
        Verdict complet avec statut, anomalies, documents manquants/valides,
        et indice de confiance calculé.
    """
    anomalies: list[Anomalie] = []

    # Règles BDC
    for regle in REGLES_BDC:
        if a := regle(dossier.bon_de_commande):
            anomalies.append(a)

    # Règles contrat
    for regle in REGLES_CONTRAT:
        if a := regle(dossier.contrat_location):
            anomalies.append(a)

    # Règles client
    if a := verifier_rfr_part(dossier.avis_imposition):
        anomalies.append(a)

    if a := verifier_justificatif_domicile(
        dossier.justificatif_domicile, date_premier_loyer
    ):
        anomalies.append(a)

    # Règles géoportail
    if a := verifier_geoportail_mode(dossier.geoportail):
        anomalies.append(a)
    if a := verifier_geoportail_distance(
        dossier.geoportail, dossier_a_geoportail=dossier.geoportail is not None
    ):
        anomalies.append(a)

    # Documents manquants / valides
    documents_manquants = _detecter_documents_manquants(dossier)
    documents_valides = _detecter_documents_valides(dossier)

    # Statut
    anomalies_bloquantes = [a for a in anomalies if a.severite == "bloquante"]
    statut: Statut = (
        "non_conforme" if documents_manquants or anomalies_bloquantes else "conforme"
    )

    indice = _calculer_indice_confiance(
        documents_valides, documents_manquants, anomalies_bloquantes
    )

    return Verdict(
        statut=statut,
        indice_confiance=indice,
        anomalies=anomalies,
        documents_manquants=documents_manquants,
        documents_valides=documents_valides,
    )


def _detecter_documents_manquants(dossier: DossierExtrait) -> list[str]:
    """Liste des types de documents ASP attendus mais absents du dossier."""
    expected = {
        "bon_de_commande": dossier.bon_de_commande,
        "contrat_location": dossier.contrat_location,
        "piece_identite": dossier.piece_identite,
        "permis_conduire": dossier.permis_conduire,
        "justificatif_domicile": dossier.justificatif_domicile,
        "avis_imposition": dossier.avis_imposition,
        "attestation_loyer": dossier.attestation_loyer,
        "attestation_engagements": dossier.attestation_engagements,
        "attestation_gros_rouleur": dossier.attestation_gros_rouleur,
        "geoportail": dossier.geoportail,
        "photos_vehicule": dossier.photos_vehicule,
        # NB: RIB et fiche de paie retirés de la liste obligatoire (cf PDF v2)
    }
    return [name for name, value in expected.items() if value is None]


def _detecter_documents_valides(dossier: DossierExtrait) -> list[str]:
    """Inverse de _detecter_documents_manquants."""
    expected = {
        "bon_de_commande": dossier.bon_de_commande,
        "contrat_location": dossier.contrat_location,
        "piece_identite": dossier.piece_identite,
        "permis_conduire": dossier.permis_conduire,
        "justificatif_domicile": dossier.justificatif_domicile,
        "avis_imposition": dossier.avis_imposition,
        "attestation_loyer": dossier.attestation_loyer,
        "attestation_engagements": dossier.attestation_engagements,
        "attestation_gros_rouleur": dossier.attestation_gros_rouleur,
        "photos_vehicule": dossier.photos_vehicule,
    }
    return [name for name, value in expected.items() if value is not None]


def _calculer_indice_confiance(
    valides: list[str],
    manquants: list[str],
    anomalies_bloquantes: list[Anomalie],
) -> int:
    """Indice de confiance 0-100 plafonné à 50 si anomalies bloquantes."""
    total = len(valides) + len(manquants)
    if total == 0:
        return 0
    base = round(len(valides) / total * 100)
    if anomalies_bloquantes:
        base = min(base, 50)
    return base
