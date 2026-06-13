"""Règles de compatibilité véhicule/site/contenant et propre/sale."""

from __future__ import annotations

from config import CLEAN_VALUE, DIRTY_VALUE
from models import Flow, Site, VehicleType


def _norm_status(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _status_matches(value: str | None, expected: str) -> bool:
    return _norm_status(value) == expected


def _status_set(flows: list[Flow]) -> set[str]:
    return {_norm_status(f.clean_dirty) for f in flows if _norm_status(f.clean_dirty)}


def _flow_allows_co_load(flow: Flow, other_statuses: set[str]) -> tuple[bool, str]:
    """Vérifie si un flux peut cohabiter simultanément avec des statuts chargés."""
    own_status = _norm_status(flow.clean_dirty)
    statuses = {s for s in other_statuses if s and s != own_status}
    if not statuses:
        return True, ""
    if not flow.mixed_allowed:
        return False, f"Flux {flow.object_key} n'autorise pas le transport mixte simultané"
    exclusion = _norm_status(flow.mixed_exclusion)
    if exclusion and exclusion in statuses:
        return False, f"Flux {flow.object_key} exclut le chargement simultané avec le statut {flow.mixed_exclusion}"
    return True, ""


def simultaneous_load_sanitary_compatible(load: list[Flow]) -> tuple[bool, str]:
    """Contrôle la compatibilité sanitaire des flux présents en même temps dans le véhicule.

    On ne rejette plus une tournée parce qu'elle contient à la fois du propre et du sale :
    c'est autorisé si ces statuts ne sont pas transportés simultanément, par exemple une
    livraison propre puis un retour sale après déchargement. Le contrôle strict est donc
    réalisé sur la charge courante, pas sur toute la tournée.
    """
    statuses = _status_set(load)
    if CLEAN_VALUE not in statuses or DIRTY_VALUE not in statuses:
        return True, ""
    for flow in load:
        ok, reason = _flow_allows_co_load(flow, statuses)
        if not ok:
            return False, reason
    return True, ""


def vehicle_state_can_load(current_state: str, flows_to_load: list[Flow], current_site: str, depot: str) -> tuple[bool, str, bool]:
    """Vérifie l'état sanitaire du véhicule avant chargement.

    Retourne (ok, raison, disinfection_needed). Une désinfection est possible uniquement
    au stationnement initial et seulement si le véhicule est vide ; elle sera matérialisée
    dans la timeline par route_builder.
    """
    statuses = _status_set(flows_to_load)
    if CLEAN_VALUE in statuses and _norm_status(current_state) == DIRTY_VALUE:
        if current_site == depot:
            return True, "", True
        return False, "Véhicule sale : retour au stationnement initial requis avant chargement propre", False
    return True, "", False


def flows_sanitary_compatible(flows: list[Flow]) -> tuple[bool, str]:
    """Compatibilité minimale, conservée pour les cas de co-chargement simultané.

    Cette fonction ne doit pas être utilisée pour rejeter toute une tournée mixte propre/sale,
    car une tournée peut être valide si le propre est livré avant la collecte du sale.
    """
    return simultaneous_load_sanitary_compatible(flows)


def vehicle_can_operate_site(vehicle: VehicleType, site: Site) -> tuple[bool, str]:
    if not site.vehicle_compat.get(vehicle.type, False):
        return False, f"{vehicle.type} incompatible avec le site {site.name} selon param Sites"
    if not site.has_dock and vehicle.manual_no_dock_min_per_container is None:
        return False, f"{vehicle.type} ne peut pas opérer sans quai sur {site.name} (manutention sans quai = NC)"
    return True, ""


def vehicle_can_transport_container(vehicle: VehicleType, container_name: str) -> tuple[bool, str]:
    if not vehicle.container_compat.get(container_name, False):
        return False, f"{vehicle.type} incompatible avec le contenant {container_name}"
    return True, ""


def vehicle_compatible_with_flow(vehicle: VehicleType, flow: Flow, sites: dict[str, Site]) -> tuple[bool, str]:
    if not vehicle.enabled:
        return False, f"{vehicle.type} désactivé"
    ok, reason = vehicle_can_transport_container(vehicle, flow.container_type)
    if not ok:
        return False, reason
    for site_name, role in [(flow.origin, "départ"), (flow.destination, "destination")]:
        site = sites.get(site_name)
        if site is None:
            return False, f"Site {role} inconnu : {site_name}"
        ok, reason = vehicle_can_operate_site(vehicle, site)
        if not ok:
            return False, reason
    return True, ""


def compatible_vehicles_for_flow(flow: Flow, vehicles: dict[str, VehicleType], sites: dict[str, Site]) -> list[VehicleType]:
    out = []
    for vehicle in vehicles.values():
        ok, _ = vehicle_compatible_with_flow(vehicle, flow, sites)
        if ok:
            out.append(vehicle)
    return out
