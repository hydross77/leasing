"""Modèles Pydantic pour les données extraites par Gemini sur chaque type de document.

Inspirés du prompt N8N v1 (cf `N8N.txt` node "Analyze document") mais durcis avec
Pydantic v2. Chaque champ est `| None` par défaut : Gemini peut ne pas trouver
l'info, on préfère `null` à une hallucination.

Les valeurs numériques (prix, loyer, distance) sont en `Decimal` pour éviter les
erreurs d'arrondi du float. Gemini les renvoie en string, on parse côté Python.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ============================================================================
# Données extraites par document
# ============================================================================


class PieceIdentite(BaseModel):
    type_piece: Literal["CNI", "passeport", "titre_sejour", "autre"] | None = None
    date_etablissement: date | None = None
    date_expiration: date | None = None
    nom_titulaire: str | None = None
    est_signee: bool | None = None


class PermisConduire(BaseModel):
    version: Literal["ancien_format_papier", "nouveau_format_carte"] | None = None
    date_etablissement: date | None = None
    date_expiration: date | None = None
    categories: list[str] = Field(default_factory=list)


class JustificatifDomicile(BaseModel):
    type_justif: str | None = Field(
        default=None, description="ex: 'facture_edf', 'quittance_loyer', 'avis_taxe'"
    )
    date_document: date | None = None
    est_facture_mobile: bool | None = Field(
        default=None,
        description="True si facture de téléphone mobile (interdit par ASP)",
    )


class AvisImposition(BaseModel):
    annee_imposition: int | None = None
    annee_revenus: int | None = None
    revenu_fiscal_reference: Decimal | None = None
    nombre_parts: Decimal | None = None


class BonDeCommande(BaseModel):
    """Extraction d'un BDC (Bon de Commande).

    Variations notées en Phase 1 :
    - Fiat : "Prix TTC en €", section "Achat" contient les options de location
    - Stellantis : logo "STELLANTIS FINANCE & SERVICES" sur les contrats associés
    """

    prix_ht: Decimal | None = None
    prix_ttc: Decimal | None = None
    nature_bdc: Literal["location", "achat", "inconnu"] | None = Field(
        default=None, description="Selon la case cochée (LLD/LOA = location)"
    )
    date_signature: date | None = None
    date_livraison_prevue: date | None = None
    montant_aide_etat: Decimal | None = None
    mention_bonus_ecologique: bool = Field(
        default=False, description="True si mention 'Bonus écologique' présente (interdit ASP)"
    )
    libelles_frais: list[str] = Field(
        default_factory=list,
        description="Liste de tous les libellés de frais détectés sur le BDC",
    )
    signature_client_presente: bool | None = None
    signature_concession_presente: bool | None = None


class ContratLocation(BaseModel):
    loueur: str | None = Field(
        default=None, description="ex: 'STELLANTIS FINANCE & SERVICES', 'RCI Banque'"
    )
    date_signature: date | None = None
    loyer_mensuel_hors_options: Decimal | None = None
    loyer_mensuel_avec_options: Decimal | None = None
    duree_mois: int | None = None
    kilometrage_annuel: int | None = None
    mention_leasing_social: bool | None = None


class AttestationLoyer(BaseModel):
    """Attestation respect des loyers — formulaire Cerfa LVEREB-1085."""

    montant_aide: Decimal | None = None
    premiere_mensualite_avant_aide: Decimal | None = None
    premiere_mensualite_apres_aide: Decimal | None = None
    mensualites_ulterieures: Decimal | None = None
    est_signee: bool | None = None


class Geoportail(BaseModel):
    distance_km: Decimal | None = None
    mode_calcul: Literal["Plus court", "Plus rapide", "autre"] | None = None
    adresse_depart: str | None = None
    adresse_arrivee: str | None = None


class PhotoVehicule(BaseModel):
    photo_vin_detectee: bool | None = None
    photo_arriere_detectee: bool | None = None
    plaque_visible: bool | None = None
    pot_echappement_visible: bool | None = None


class AttestationGrosRouleur(BaseModel):
    adresse_client: str | None = None
    adresse_employeur: str | None = None
    cachet_employeur: bool | None = None
    est_signee: bool | None = None


class AttestationEngagements(BaseModel):
    """Attestation respect des engagements — formulaire Cerfa officiel LVEREB-1085."""

    cases_cochees: list[str] = Field(default_factory=list)
    est_signee: bool | None = None


# ============================================================================
# Dossier complet
# ============================================================================


class DossierExtrait(BaseModel):
    """Agrégat des données extraites pour un dossier entier.

    Toutes les pièces sont optionnelles : si Gemini ne trouve pas un document
    dans le dossier, le champ reste `None` et la règle métier déclarera
    « document manquant ».
    """

    opportunity_id: str
    opportunity_name: str
    marque: str
    concession: str

    bon_de_commande: BonDeCommande | None = None
    contrat_location: ContratLocation | None = None
    piece_identite: PieceIdentite | None = None
    permis_conduire: PermisConduire | None = None
    justificatif_domicile: JustificatifDomicile | None = None
    avis_imposition: AvisImposition | None = None
    attestation_loyer: AttestationLoyer | None = None
    attestation_engagements: AttestationEngagements | None = None
    attestation_gros_rouleur: AttestationGrosRouleur | None = None
    geoportail: Geoportail | None = None
    photos_vehicule: PhotoVehicule | None = None
