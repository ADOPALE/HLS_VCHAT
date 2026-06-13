"""Configuration technique d'OptiFLUX.

Ce module centralise uniquement les constantes techniques : noms d'onglets,
colonnes attendues, synonymes de colonnes et valeurs de domaine considérées
comme invariantes. Les noms métier de sites, véhicules, contenants et fonctions
support sont lus dynamiquement depuis le fichier Excel.
"""

from __future__ import annotations

SHEET_RH = "param RH"
SHEET_SITES = "param Sites"
SHEET_VEHICLES = "param Véhicules"
SHEET_CONTAINERS = "param Contenants"
SHEET_DURATION = "matrice Durée"
SHEET_DISTANCE = "matrice Dist"
SHEET_LISTS = "LISTES"
SHEET_FLOWS = "M flux"

EXPECTED_SHEETS = [
    SHEET_RH,
    SHEET_SITES,
    SHEET_VEHICLES,
    SHEET_DURATION,
    SHEET_DISTANCE,
    SHEET_LISTS,
    SHEET_CONTAINERS,
    SHEET_FLOWS,
]

# Valeurs invariantes du domaine, centralisées ici pour éviter leur dispersion.
YES_VALUES = {"oui", "o", "yes", "y", "true", "vrai", "1"}
NO_VALUES = {"non", "n", "no", "false", "faux", "0"}
NC_VALUES = {"nc", "n/c", "non concerne", "non concerné", "na", "n/a"}
VOLUME_VALUE = "volume"
FREQUENCIES_VALUE = "fréquences"
CLEAN_VALUE = "propre"
DIRTY_VALUE = "sale"
FULL_VALUE = "plein"
EMPTY_VALUE = "vide"

WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
WEEKEND_DAYS = {"Samedi", "Dimanche"}
QUANTITY_PREFIX = "Quantité"

# Paramètres opérationnels constants.
PICKUP_PREP_MIN = 15
END_OF_SHIFT_MIN = 10
DISINFECTION_MIN = 15
DEFAULT_DOCK_CAPACITY = 1
MAX_GAP_HORAIRE_CIRCUIT = 240
DEFAULT_OPTIM_TIME_LIMIT_SEC = 600
EPS = 1e-9

# Aliases de colonnes réels constatés dans le modèle + variantes tolérées.
COL_ALIASES = {
    "site_name": ["Libellé", "Libelle", "Site", "Nom du site"],
    "site_address": ["Adresses", "Adresse"],
    "site_has_dock": ["Présence de quai", "Presence de quai", "Quai"],
    "site_dock_capacity": ["Capacité quai", "Capacite quai", "Capacité simultanée de mise à quai"],
    "vehicle_type": ["Types", "Type", "Type de véhicule", "Type vehicule"],
    "vehicle_initial_site": ["Stationnement initial", "Site de stationnement initial", "Dépôt", "Depot"],
    "vehicle_length": ["dim longueur interne (m)", "Longueur interne (m)", "Longueur utile (m)"],
    "vehicle_width": ["dim largeur interne (m)", "Largeur interne (m)", "Largeur utile (m)"],
    "vehicle_height": ["dim hauteur interne (m)", "Hauteur interne (m)", "Hauteur utile (m)"],
    "vehicle_max_weight": ["Poids max chargement", "Poids max chargement (T)", "Poids maximal de chargement"],
    "vehicle_consumption": ["Consommation (L/km)", "Consommation"],
    "vehicle_fuel_cost": ["Cout carburant (€/km)", "Coût carburant (€/km)", "Cout carburant"],
    "vehicle_co2": ["Cout carbone (kg/km)", "Coût carbone (kg/km)", "Emission CO2 (kg/km)"],
    "vehicle_tail_lift": ["Présence hayon", "Presence hayon", "Hayon"],
    "vehicle_dock_time": ["Temps de mise à quai - manœuvre, contact/admin (minutes)", "Temps de mise à quai", "Temps mise à quai"],
    "vehicle_manual_no_dock": ["Manutention sans quai (minutes / contenants)", "Manutention sans quai"],
    "vehicle_manual_dock": ["Manutention avec quai (minutes / contenants)", "Manutention avec quai"],
    "container_name": ["libellé", "Libellé", "Libelle", "Nature de contenant", "Contenant"],
    "container_length": ["dim longueur (m)", "Longueur (m)"],
    "container_width": ["dim largeur (m)", "Largeur (m)"],
    "container_empty_weight": ["Poids vide (T)", "Poids vide"],
    "container_full_weight": ["Poids plein (T)", "Poids plein"],
    "flow_origin": ["Point de départ", "Point de depart", "Origine"],
    "flow_destination": ["Point de destination", "Destination"],
    "flow_function": ["Fonction Support associée", "Fonction support associée", "Fonction support"],
    "flow_label": ["Nature du Flux \n(champ libre)", "Nature du Flux (champ libre)", "Nature du flux", "Libellé flux"],
    "flow_container": ["Nature de contenant", "Contenant", "Type de contenant"],
    "flow_full_empty": ["Plein / vide", "Plein/vide"],
    "flow_clean_dirty": ["Sale / propre", "Sale/propre", "Statut sanitaire"],
    "flow_round_trip": ["Aller/Retour", "Aller / Retour"],
    "flow_mixed_allowed": ["Transport mixte possible (OUI / NON)", "Transport mixte possible", "Mixte possible"],
    "flow_mixed_exclusion": ["Règles d'exclusions si transport mixte", "Regles d'exclusions si transport mixte", "Exclusion mixte"],
    "flow_mutualized": ["Tournées mutualisées ? (OUI / NON)", "Tournees mutualisees ? (OUI / NON)", "Tournées mutualisées ?"],
    "flow_mutualized_name": ["Nom de la tournée mutualisée le cas échéant", "Nom de la tournee mutualisee le cas echeant", "Nom de la tournée mutualisée"],
    "flow_nature": ["Nature du flux (les tournées sont elles à prévoir avec une obligation de transport ou une obligation de passage?)", "Nature du flux"],
    "flow_week_start": ["Plage horaire en semaine (Heure début)", "Plage horaire en semaine (Heure debut)"],
    "flow_week_end": ["Plage horaire en semaine (Heure fin)"],
    "flow_we_start": ["Plage horaire en Week END (Heure début)", "Plage horaire en Week END (Heure debut)"],
    "flow_we_end": ["Plage horaire en Week END (Heure fin)"],
    "flow_ready_time": ["Heure de mise à disposition min départ", "Heure de mise a disposition min depart", "Heure mise à disposition"],
    "flow_due_time": ["Heure max de livraison à la destination", "Heure max livraison", "Heure limite livraison"],
    "flow_priority": ["Urgence / flux prioritaire \n(Oui/Non)", "Urgence / flux prioritaire (Oui/Non)", "Urgence / flux prioritaire"],
    "rh_vacation": ["Format horaire", "Durée de vacation", "Duree de vacation"],
    "rh_pause": ["Pause", "Durée de pause", "Duree de pause"],
    "rh_start_min": ["heure début mini", "Heure début mini", "heure debut mini"],
    "rh_end_max": ["heure fin max", "Heure fin max"],
}

REQUIRED_COLUMNS = {
    SHEET_RH: ["rh_vacation", "rh_pause", "rh_start_min", "rh_end_max"],
    SHEET_SITES: ["site_name", "site_address", "site_has_dock"],
    SHEET_VEHICLES: [
        "vehicle_type",
        "vehicle_initial_site",
        "vehicle_length",
        "vehicle_width",
        "vehicle_height",
        "vehicle_max_weight",
        "vehicle_consumption",
        "vehicle_fuel_cost",
        "vehicle_co2",
        "vehicle_tail_lift",
        "vehicle_dock_time",
        "vehicle_manual_no_dock",
        "vehicle_manual_dock",
    ],
    SHEET_CONTAINERS: [
        "container_name",
        "container_length",
        "container_width",
        "container_empty_weight",
        "container_full_weight",
    ],
    SHEET_FLOWS: [
        "flow_origin",
        "flow_destination",
        "flow_function",
        "flow_container",
        "flow_full_empty",
        "flow_clean_dirty",
        "flow_mixed_allowed",
        "flow_mixed_exclusion",
        "flow_mutualized_name",
        "flow_nature",
        "flow_ready_time",
        "flow_due_time",
    ],
}
