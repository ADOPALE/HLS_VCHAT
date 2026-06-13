"""Contrôles de cohérence import et contrôles de solution."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from config import SHEET_DISTANCE, SHEET_DURATION, SHEET_FLOWS, SHEET_SITES, SHEET_VEHICLES
from data_loader import OptiFluxData, _ns
from exceptions import Diagnostic, ImportBlockingError
from models import DayResult, RHParams


def validate_import_data(data: OptiFluxData) -> list[Diagnostic]:
    """Contrôle les référentiels importés et lève une exception si bloquant."""
    diagnostics: list[Diagnostic] = []

    site_names = set(data.sites.keys())
    veh_names = set(data.vehicles.keys())
    cont_names = set(data.containers.keys())
    dur_sites = {a for a, _ in data.duration_matrix.keys()} | {b for _, b in data.duration_matrix.keys()}
    dist_sites = {a for a, _ in data.distance_matrix.keys()} | {b for _, b in data.distance_matrix.keys()}

    if dur_sites != dist_sites:
        diagnostics.append(Diagnostic(SHEET_DURATION, None, None, "CRITIQUE", "MATRICES_DIVERGENTES", "Les matrices Durée et Dist ne couvrent pas exactement les mêmes sites."))
    if not site_names.issubset(dur_sites):
        missing = sorted(site_names - dur_sites)
        diagnostics.append(Diagnostic(SHEET_DURATION, None, None, "CRITIQUE", "SITES_ABSENTS_MATRICE_DUREE", f"Sites absents de la matrice Durée : {missing}"))
    if not site_names.issubset(dist_sites):
        missing = sorted(site_names - dist_sites)
        diagnostics.append(Diagnostic(SHEET_DISTANCE, None, None, "CRITIQUE", "SITES_ABSENTS_MATRICE_DIST", f"Sites absents de la matrice Dist : {missing}"))

    for vt, vehicle in data.vehicles.items():
        if not vehicle.initial_site:
            diagnostics.append(Diagnostic(SHEET_VEHICLES, None, None, "CRITIQUE", "STATIONNEMENT_INITIAL_ABSENT", f"Le véhicule {vt} n'a pas de stationnement initial."))
        elif vehicle.initial_site not in site_names:
            diagnostics.append(Diagnostic(SHEET_VEHICLES, None, None, "CRITIQUE", "STATIONNEMENT_INITIAL_INCONNU", f"Stationnement initial inconnu pour {vt}: {vehicle.initial_site}"))

    for site in data.sites.values():
        for vt in veh_names:
            if vt not in site.vehicle_compat:
                # Alerte uniquement : un véhicule ajouté peut ne pas avoir encore sa colonne dans param Sites.
                diagnostics.append(Diagnostic(SHEET_SITES, None, None, "ALERTE", "COMPAT_SITE_VEHICULE_ABSENTE", f"Compatibilité site/véhicule absente pour site {site.name} et véhicule {vt}.", "Ajouter une colonne dans param Sites si ce véhicule doit être utilisable."))
            elif site.vehicle_compat.get(vt) and not site.has_dock and data.vehicles[vt].manual_no_dock_min_per_container is None:
                diagnostics.append(Diagnostic(SHEET_SITES, None, None, "ALERTE", "CONTRADICTION_SANS_QUAI", f"{site.name} est sans quai et compatible avec {vt}, mais la manutention sans quai du véhicule est NC. La compatibilité param Sites fera foi."))

    rh_diags = validate_rh(data.rh)
    diagnostics.extend(rh_diags)

    blocking = [d for d in diagnostics if d.severity == "CRITIQUE"]
    if blocking:
        raise ImportBlockingError(blocking)
    return diagnostics


def validate_rh(rh: RHParams) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if rh.pause_duration >= rh.vacation_duration:
        diagnostics.append(Diagnostic("param RH", None, None, "CRITIQUE", "RH_PAUSE_INVALIDE", "La pause doit être inférieure à la durée de vacation."))
    if rh.start_min + rh.vacation_duration > rh.end_max:
        diagnostics.append(Diagnostic("param RH", None, None, "CRITIQUE", "RH_AMPLITUDE_INVALIDE", "Heure début mini + vacation dépasse l'heure fin max."))
    return diagnostics


def validate_solution(result: DayResult) -> list[dict]:
    """Vérifie les invariants principaux de la solution produite."""
    controls: list[dict] = list(result.controls)
    for post in result.posts:
        if post.end_min - post.start_min > result.indicators.get("vacation_duration", 10**9):
            controls.append({"Jour": result.day, "Type de contrôle": "DEPASSEMENT_VACATION", "Statut": "ERREUR", "Détail": f"{post.post_id} dépasse la vacation", "Gravité": "ERREUR", "Action recommandée": "Relancer avec plus de véhicules ou revoir les fenêtres."})
        if post.end_min > result.indicators.get("heure_fin_max", 10**9):
            controls.append({"Jour": result.day, "Type de contrôle": "DEPASSEMENT_END_MAX", "Statut": "ERREUR", "Détail": f"{post.post_id} finit après l'heure maximale", "Gravité": "CRITIQUE", "Action recommandée": "Revoir les paramètres RH."})
    if result.unserved_flows:
        controls.append({"Jour": result.day, "Type de contrôle": "FLUX_NON_SERVI", "Statut": "ERREUR", "Détail": f"{len(result.unserved_flows)} flux non servis", "Gravité": "CRITIQUE", "Action recommandée": "Consulter l'onglet Flux non servis."})
    if not any(c["Type de contrôle"] == "SOLUTION_VALIDEE" for c in controls):
        status = "OK" if not [c for c in controls if c.get("Statut") == "ERREUR"] else "ERREUR"
        controls.append({"Jour": result.day, "Type de contrôle": "SOLUTION_VALIDEE", "Statut": status, "Détail": "Contrôles finaux exécutés", "Gravité": status, "Action recommandée": None})
    return controls
