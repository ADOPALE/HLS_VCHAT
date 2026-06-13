"""Règles de compatibilité véhicule/site/contenant et propre/sale."""

from __future__ import annotations

from config import CLEAN_VALUE, DIRTY_VALUE
from models import Flow, Site, VehicleType


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


def flows_sanitary_compatible(flows: list[Flow]) -> tuple[bool, str]:
    """Vérifie les règles de mixité propre/sale dans un même circuit."""
    statuses = {str(f.clean_dirty).strip().casefold() for f in flows}
    if CLEAN_VALUE in statuses and DIRTY_VALUE in statuses:
        for flow in flows:
            exclusion = (flow.mixed_exclusion or "").strip().casefold()
            status = str(flow.clean_dirty).strip().casefold()
            if not flow.mixed_allowed:
                return False, f"Flux {flow.object_key} n'autorise pas le transport mixte"
            if exclusion and exclusion in statuses and exclusion != status:
                return False, f"Flux {flow.object_key} exclut le statut sanitaire {flow.mixed_exclusion}"
    return True, ""


def compatible_vehicles_for_flow(flow: Flow, vehicles: dict[str, VehicleType], sites: dict[str, Site]) -> list[VehicleType]:
    out = []
    for vehicle in vehicles.values():
        ok, _ = vehicle_compatible_with_flow(vehicle, flow, sites)
        if ok:
            out.append(vehicle)
    return out
