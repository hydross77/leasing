"""Tests unitaires des règles ASP 2025 (Phase 3).

Structure :
1. Tests par règle (cas conforme + cas non conforme + edge cases)
2. Tests d'orchestration (verifier_dossier)
3. Tests de non-régression des 10 anomalies v1 (cf ameliorations-v2.md §1)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.verification import (
    verifier_aide_plafond,
    verifier_aide_ratio_ttc,
    verifier_bonus_ecologique_interdit,
    verifier_date_debut_dispositif,
    verifier_delai_bdc_livraison,
    verifier_dossier,
    verifier_duree_location,
    verifier_frais_autorises,
    verifier_geoportail_distance,
    verifier_geoportail_mode,
    verifier_justificatif_domicile,
    verifier_kilometrage,
    verifier_loyer_hors_options,
    verifier_rfr_part,
)
from app.models.document import (
    AttestationEngagements,
    AttestationGrosRouleur,
    AttestationLoyer,
    AvisImposition,
    BonDeCommande,
    ContratLocation,
    DossierExtrait,
    Geoportail,
    JustificatifDomicile,
    PermisConduire,
    PhotoVehicule,
    PieceIdentite,
)


def _bdc_ok(**overrides) -> BonDeCommande:
    """BDC totalement conforme — facile à dériver pour chaque test."""
    base = {
        "prix_ht": Decimal("24000"),
        "prix_ttc": Decimal("28800"),
        "nature_bdc": "location",
        "date_signature": date(2025, 11, 15),
        "date_livraison_prevue": date(2025, 12, 15),
        "montant_aide_etat": Decimal("7000"),
        "mention_bonus_ecologique": False,
        "libelles_frais": ["carte grise", "frais de mise à la route"],
        "signature_client_presente": True,
        "signature_concession_presente": True,
    }
    base.update(overrides)
    return BonDeCommande(**base)


def _contrat_ok(**overrides) -> ContratLocation:
    base = {
        "loueur": "STELLANTIS FINANCE & SERVICES",
        "date_signature": date(2025, 11, 20),
        "loyer_mensuel_hors_options": Decimal("196.96"),
        "loyer_mensuel_avec_options": Decimal("268.14"),
        "duree_mois": 36,
        "kilometrage_annuel": 12_000,
        "mention_leasing_social": True,
    }
    base.update(overrides)
    return ContratLocation(**base)


# ============================================================================
# A001 — RFR / parts
# ============================================================================


class TestRfrPart:
    def test_rfr_conforme_18624_sur_2_parts(self):
        """Cas réel anomalie v1 A1 : 18 624 / 2 = 9 312 €/part = conforme."""
        avis = AvisImposition(
            revenu_fiscal_reference=Decimal("18624"), nombre_parts=Decimal("2")
        )
        assert verifier_rfr_part(avis) is None

    def test_rfr_au_seuil_exact(self):
        """16 300 / 1 = 16 300 €/part = exactement au seuil → conforme."""
        avis = AvisImposition(
            revenu_fiscal_reference=Decimal("16300"), nombre_parts=Decimal("1")
        )
        assert verifier_rfr_part(avis) is None

    def test_rfr_depasse_seuil(self):
        avis = AvisImposition(
            revenu_fiscal_reference=Decimal("20000"), nombre_parts=Decimal("1")
        )
        a = verifier_rfr_part(avis)
        assert a is not None
        assert a.code == "A001_rfr_part"
        assert "20000" in a.detail

    def test_zero_parts_remonte_anomalie(self):
        avis = AvisImposition(
            revenu_fiscal_reference=Decimal("10000"), nombre_parts=Decimal("0")
        )
        a = verifier_rfr_part(avis)
        assert a is not None
        assert "zéro" in a.detail.lower() or "0" in a.detail

    def test_avis_absent_pas_anomalie_ici(self):
        """Si avis manquant, anomalie levée par 'document manquant', pas ici."""
        assert verifier_rfr_part(None) is None


# ============================================================================
# A005-A006 — Aide État
# ============================================================================


class TestAideTTC:
    def test_aide_27pct_du_ttc_conforme(self):
        """Cas réel anomalie v1 A5 : aide 7000 € sur 26 000 € TTC = 26.9% → conforme."""
        bdc = _bdc_ok(prix_ttc=Decimal("26000"), montant_aide_etat=Decimal("7000"))
        assert verifier_aide_ratio_ttc(bdc) is None

    def test_aide_calculee_sur_ht_doit_etre_ignoree(self):
        """Cas réel v1 : aide 7000 / HT 23 422 € = 29.9% MAIS aide 7000 / TTC 28 800 € = 24.3% → conforme."""
        bdc = _bdc_ok(prix_ht=Decimal("23422"), prix_ttc=Decimal("28800"), montant_aide_etat=Decimal("7000"))
        assert verifier_aide_ratio_ttc(bdc) is None

    def test_aide_depasse_27pct_ttc(self):
        bdc = _bdc_ok(prix_ttc=Decimal("20000"), montant_aide_etat=Decimal("7000"))
        a = verifier_aide_ratio_ttc(bdc)
        assert a is not None
        assert a.code == "A005_aide_27_ttc"

    def test_aide_plafond_7000_conforme(self):
        bdc = _bdc_ok(montant_aide_etat=Decimal("7000"))
        assert verifier_aide_plafond(bdc) is None

    def test_aide_plafond_depasse(self):
        bdc = _bdc_ok(montant_aide_etat=Decimal("7500"))
        a = verifier_aide_plafond(bdc)
        assert a is not None
        assert a.code == "A006_aide_plafond"


# ============================================================================
# A007 — Bonus écologique interdit
# ============================================================================


class TestBonusEcologique:
    def test_bdc_sans_bonus_ecologique_conforme(self):
        bdc = _bdc_ok(mention_bonus_ecologique=False)
        assert verifier_bonus_ecologique_interdit(bdc) is None

    def test_bdc_avec_bonus_ecologique_non_conforme(self):
        bdc = _bdc_ok(mention_bonus_ecologique=True)
        a = verifier_bonus_ecologique_interdit(bdc)
        assert a is not None
        assert a.code == "A007_bonus_ecologique"


# ============================================================================
# A008 — Frais autorisés (PDF v2 — non-régression v1)
# ============================================================================


class TestFraisAutorises:
    def test_carte_grise_autorisee(self):
        bdc = _bdc_ok(libelles_frais=["Carte Grise"])
        assert verifier_frais_autorises(bdc) is None

    def test_immatriculation_autorisee_regression_v1(self):
        """Cas réel anomalie v1 A6 : 'frais d'immatriculation' ne doit pas alerter."""
        bdc = _bdc_ok(libelles_frais=["Frais d'immatriculation 313,76 €"])
        assert verifier_frais_autorises(bdc) is None

    def test_pack_livraison_autorise_regression_v1(self):
        """Cas réel anomalie v1 A6 : 'pack livraison' = frais de préparation OK."""
        bdc = _bdc_ok(libelles_frais=["Pack livraison", "Carte Grise"])
        assert verifier_frais_autorises(bdc) is None

    def test_frais_de_preparation_autorises(self):
        bdc = _bdc_ok(libelles_frais=["Frais de préparation du véhicule"])
        assert verifier_frais_autorises(bdc) is None

    def test_frais_administratifs_purs_non_autorises(self):
        bdc = _bdc_ok(libelles_frais=["Frais administratifs annuels"])
        a = verifier_frais_autorises(bdc)
        assert a is not None
        assert a.code == "A008_frais_interdits"


# ============================================================================
# A009-A010 — Dates BDC
# ============================================================================


class TestDatesBdc:
    def test_delai_bdc_livraison_3_mois_conforme(self):
        bdc = _bdc_ok(
            date_signature=date(2025, 9, 30),
            date_livraison_prevue=date(2025, 12, 15),
        )
        assert verifier_delai_bdc_livraison(bdc) is None

    def test_delai_bdc_livraison_6_mois_pile_conforme(self):
        """Cas réel anomalie v1 A8 : BDC 30/09/2025 + livraison déc 2025 = OK."""
        bdc = _bdc_ok(
            date_signature=date(2025, 9, 30),
            date_livraison_prevue=date(2025, 12, 31),
        )
        assert verifier_delai_bdc_livraison(bdc) is None

    def test_delai_bdc_livraison_au_dela_de_6_mois(self):
        bdc = _bdc_ok(
            date_signature=date(2025, 9, 30),
            date_livraison_prevue=date(2026, 5, 1),  # +7 mois
        )
        a = verifier_delai_bdc_livraison(bdc)
        assert a is not None
        assert a.code == "A009_delai_6_mois"

    def test_bdc_apres_30_sept_2025_conforme(self):
        bdc = _bdc_ok(date_signature=date(2025, 10, 1))
        assert verifier_date_debut_dispositif(bdc) is None

    def test_bdc_avant_30_sept_2025_non_conforme(self):
        bdc = _bdc_ok(date_signature=date(2025, 8, 15))
        a = verifier_date_debut_dispositif(bdc)
        assert a is not None
        assert a.code == "A010_avant_dispositif"


# ============================================================================
# A011-A013 — Contrat de location
# ============================================================================


class TestContratLocation:
    def test_loyer_hors_options_19696_conforme(self):
        """Cas réel anomalie v1 A10 : 196,96 € hors options + 268,14 € avec options → conforme."""
        contrat = _contrat_ok(
            loyer_mensuel_hors_options=Decimal("196.96"),
            loyer_mensuel_avec_options=Decimal("268.14"),
        )
        assert verifier_loyer_hors_options(contrat) is None

    def test_loyer_hors_options_200_pile_non_conforme(self):
        """200 € pile = NON conforme (strictement < 200 €)."""
        contrat = _contrat_ok(loyer_mensuel_hors_options=Decimal("200"))
        a = verifier_loyer_hors_options(contrat)
        assert a is not None
        assert a.code == "A011_loyer_max"

    def test_loyer_hors_options_201_non_conforme(self):
        contrat = _contrat_ok(loyer_mensuel_hors_options=Decimal("201"))
        a = verifier_loyer_hors_options(contrat)
        assert a is not None
        assert a.code == "A011_loyer_max"

    def test_loyer_avec_options_ignore_pour_la_regle(self):
        """La règle utilise STRICTEMENT le hors_options même si avec_options > 200."""
        contrat = _contrat_ok(
            loyer_mensuel_hors_options=Decimal("180"),
            loyer_mensuel_avec_options=Decimal("450"),  # avec options élevé
        )
        assert verifier_loyer_hors_options(contrat) is None

    def test_duree_36_mois_conforme(self):
        contrat = _contrat_ok(duree_mois=36)
        assert verifier_duree_location(contrat) is None

    def test_duree_35_mois_non_conforme(self):
        contrat = _contrat_ok(duree_mois=35)
        a = verifier_duree_location(contrat)
        assert a is not None
        assert a.code == "A012_duree_location"

    def test_km_12000_conforme(self):
        contrat = _contrat_ok(kilometrage_annuel=12_000)
        assert verifier_kilometrage(contrat) is None

    def test_km_11999_non_conforme(self):
        contrat = _contrat_ok(kilometrage_annuel=11_999)
        a = verifier_kilometrage(contrat)
        assert a is not None
        assert a.code == "A013_kilometrage"


# ============================================================================
# A020-A021 — Justificatif de domicile
# ============================================================================


class TestJustificatifDomicile:
    def test_facture_edf_recente_conforme(self):
        justif = JustificatifDomicile(
            type_justif="facture EDF",
            date_document=date(2026, 5, 1),
            est_facture_mobile=False,
        )
        assert verifier_justificatif_domicile(justif, date(2026, 5, 13)) is None

    def test_facture_mobile_non_conforme(self):
        justif = JustificatifDomicile(
            type_justif="facture mobile Orange",
            est_facture_mobile=True,
        )
        a = verifier_justificatif_domicile(justif, date(2026, 5, 13))
        assert a is not None
        assert a.code == "A020_justif_mobile"

    def test_justif_3_mois_pile_conforme(self):
        justif = JustificatifDomicile(
            type_justif="quittance loyer",
            date_document=date(2026, 2, 13),
            est_facture_mobile=False,
        )
        # 13/02/26 → 13/05/26 = exactement 3 mois
        assert verifier_justificatif_domicile(justif, date(2026, 5, 13)) is None

    def test_justif_4_mois_non_conforme(self):
        justif = JustificatifDomicile(
            type_justif="facture EDF",
            date_document=date(2026, 1, 1),
            est_facture_mobile=False,
        )
        a = verifier_justificatif_domicile(justif, date(2026, 5, 13))
        assert a is not None
        assert a.code == "A021_justif_anciennete"


# ============================================================================
# A030-A033 — Géoportail
# ============================================================================


class TestGeoportail:
    def test_mode_plus_court_conforme(self):
        geo = Geoportail(distance_km=Decimal("20"), mode_calcul="Plus court")
        assert verifier_geoportail_mode(geo) is None

    def test_mode_plus_rapide_non_conforme(self):
        geo = Geoportail(distance_km=Decimal("20"), mode_calcul="Plus rapide")
        a = verifier_geoportail_mode(geo)
        assert a is not None
        assert a.code == "A030_geoportail_mode"

    def test_distance_inf_15_avec_geoportail_conforme(self):
        geo = Geoportail(distance_km=Decimal("10"), mode_calcul="Plus court")
        assert verifier_geoportail_distance(geo, dossier_a_geoportail=True) is None

    def test_zone_surveillance_alerte_non_bloquante(self):
        geo = Geoportail(distance_km=Decimal("16"), mode_calcul="Plus court")
        a = verifier_geoportail_distance(geo, dossier_a_geoportail=True)
        assert a is not None
        assert a.code == "A032_zone_surveillance"
        assert a.severite == "alerte"

    def test_distance_excessive_alerte_non_bloquante(self):
        geo = Geoportail(distance_km=Decimal("150"), mode_calcul="Plus court")
        a = verifier_geoportail_distance(geo, dossier_a_geoportail=True)
        assert a is not None
        assert a.code == "A033_distance_excessive"
        assert a.severite == "alerte"


# ============================================================================
# Orchestrateur — verifier_dossier
# ============================================================================


def _dossier_ok() -> DossierExtrait:
    """Dossier intégralement conforme — base pour les tests d'orchestration."""
    return DossierExtrait(
        opportunity_id="006Tn00000ABC123IAF",
        opportunity_name="DUPONT Marie - 12-05-2026",
        marque="fiat",
        concession="Fiat Mulhouse",
        bon_de_commande=_bdc_ok(),
        contrat_location=_contrat_ok(),
        piece_identite=PieceIdentite(
            type_piece="CNI",
            date_etablissement=date(2020, 1, 1),
            date_expiration=date(2030, 1, 1),
        ),
        permis_conduire=PermisConduire(
            version="nouveau_format_carte",
            date_etablissement=date(2018, 6, 1),
            date_expiration=date(2033, 6, 1),
        ),
        justificatif_domicile=JustificatifDomicile(
            type_justif="facture EDF",
            date_document=date(2026, 4, 1),
            est_facture_mobile=False,
        ),
        avis_imposition=AvisImposition(
            annee_imposition=2025,
            revenu_fiscal_reference=Decimal("18624"),
            nombre_parts=Decimal("2"),
        ),
        attestation_loyer=AttestationLoyer(
            montant_aide=Decimal("7000"),
            premiere_mensualite_avant_aide=Decimal("7000"),
            premiere_mensualite_apres_aide=Decimal("0"),
            mensualites_ulterieures=Decimal("196.96"),
            est_signee=True,
        ),
        attestation_engagements=AttestationEngagements(
            cases_cochees=["non_cumul_bonus", "pas_de_caution"], est_signee=True
        ),
        attestation_gros_rouleur=AttestationGrosRouleur(
            adresse_client="10 rue X", adresse_employeur="20 rue Y", est_signee=True
        ),
        geoportail=Geoportail(
            distance_km=Decimal("25"),
            mode_calcul="Plus court",
            adresse_depart="Mulhouse",
            adresse_arrivee="Bâle",
        ),
        photos_vehicule=PhotoVehicule(
            photo_vin_detectee=True,
            photo_arriere_detectee=True,
            plaque_visible=True,
            pot_echappement_visible=False,
        ),
    )


class TestVerifierDossier:
    def test_dossier_complet_et_conforme(self):
        verdict = verifier_dossier(_dossier_ok(), date_premier_loyer=date(2026, 5, 13))
        assert verdict.statut == "conforme"
        assert verdict.indice_confiance == 100
        assert verdict.anomalies == []
        assert verdict.documents_manquants == []

    def test_dossier_avec_anomalie_bdc_non_conforme(self):
        dossier = _dossier_ok()
        dossier.bon_de_commande = _bdc_ok(mention_bonus_ecologique=True)
        verdict = verifier_dossier(dossier, date_premier_loyer=date(2026, 5, 13))
        assert verdict.statut == "non_conforme"
        codes = [a.code for a in verdict.anomalies]
        assert "A007_bonus_ecologique" in codes
        assert verdict.indice_confiance <= 50  # plafonné car bloquant

    def test_dossier_avec_document_manquant(self):
        dossier = _dossier_ok()
        dossier.geoportail = None
        verdict = verifier_dossier(dossier, date_premier_loyer=date(2026, 5, 13))
        assert verdict.statut == "non_conforme"
        assert "geoportail" in verdict.documents_manquants


# ============================================================================
# Non-régression des anomalies v1 (cf ameliorations-v2.md §1)
# ============================================================================


class TestNonRegressionAnomaliesV1:
    """Ces 5 cas viennent de production v1 et NE DOIVENT PLUS remonter d'anomalie."""

    def test_A1_rfr_18624_sur_2_parts_conforme(self):
        """Renault Mulhouse / Zakaria MAJDOUNE — RFR/part conforme."""
        avis = AvisImposition(
            revenu_fiscal_reference=Decimal("18624"), nombre_parts=Decimal("2")
        )
        assert verifier_rfr_part(avis) is None

    def test_A5_aide_7000_sur_26000_ttc_conforme(self):
        """Renault Illkirch / MOUNIR BOUKKAZA — aide ratio sur TTC, pas HT."""
        bdc = _bdc_ok(prix_ttc=Decimal("26000"), montant_aide_etat=Decimal("7000"))
        # 7000/26000 = 26.9% < 27% → conforme
        assert verifier_aide_ratio_ttc(bdc) is None

    def test_A6_immatriculation_pack_livraison_conformes(self):
        """Renault Colmar + Peugeot Reims — frais immat/pack livraison autorisés."""
        bdc = _bdc_ok(
            libelles_frais=[
                "Frais d'immatriculation",
                "Pack livraison",
                "Frais de préparation",
            ]
        )
        assert verifier_frais_autorises(bdc) is None

    def test_A8_delai_30sept_a_dec_2025_conforme(self):
        """Renault Mulhouse / Camille GAULT — BDC 30/09/25 + livraison déc 25 OK."""
        bdc = _bdc_ok(
            date_signature=date(2025, 9, 30),
            date_livraison_prevue=date(2025, 12, 15),
        )
        assert verifier_delai_bdc_livraison(bdc) is None

    def test_A10_loyer_19696_hors_options_conforme(self):
        """Fiat Mulhouse / Mohamed RIAD — 196,96 € hors options conforme malgré 268,14 € avec options."""
        contrat = _contrat_ok(
            loyer_mensuel_hors_options=Decimal("196.96"),
            loyer_mensuel_avec_options=Decimal("268.14"),
        )
        assert verifier_loyer_hors_options(contrat) is None
