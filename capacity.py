"""Calcul des capacités véhicules/contenants.

La capacité est calculée en 2D avec rotation du contenant. La hauteur n'est pas
utilisée car absente du référentiel contenant, conformément aux hypothèses du
prompt.
"""

from __future__ import annotations

import math

from config import FULL_VALUE
from models import ContainerType, Flow, VehicleType


def discrete_floor_capacity(vehicle: VehicleType, container: ContainerType) -> int:
    """Nombre maximal de contenants au plancher avec test des deux orientations."""
    if vehicle.length_m <= 0 or vehicle.width_m <= 0 or container.length_m <= 0 or container.width_m <= 0:
        return 0
    cap1 = math.floor(vehicle.length_m / container.length_m) * math.floor(vehicle.width_m / container.width_m)
    cap2 = math.floor(vehicle.length_m / container.width_m) * math.floor(vehicle.width_m / container.length_m)
    return int(max(cap1, cap2))


def container_weight_for_flow(container: ContainerType, flow: Flow) -> float:
    """Poids à retenir selon le statut plein/vide du flux."""
    return container.full_weight_t if str(flow.full_empty).strip().casefold() == FULL_VALUE else container.empty_weight_t


def max_containers_by_weight(vehicle: VehicleType, container: ContainerType, flow: Flow) -> int:
    weight = container_weight_for_flow(container, flow)
    if weight <= 0:
        return 10**9
    return int(math.floor(vehicle.max_weight_t / weight))


def max_containers_for_flow(vehicle: VehicleType, container: ContainerType, flow: Flow) -> int:
    """Capacité en contenants pour un flux donné, surface et poids combinés."""
    return max(0, min(discrete_floor_capacity(vehicle, container), max_containers_by_weight(vehicle, container, flow)))


def surface_fraction(vehicle: VehicleType, container: ContainerType, qty: int) -> float:
    """Fraction de capacité discrète consommée par un chargement d'un type de contenant."""
    cap = discrete_floor_capacity(vehicle, container)
    if cap <= 0:
        return float("inf")
    return qty / cap


def load_ok(vehicle: VehicleType, containers: dict[str, ContainerType], load: list[Flow]) -> tuple[bool, str, float, float]:
    """Vérifie la capacité instantanée d'un véhicule pour les flux chargés.

    Retourne : ok, raison, taux surfacique %, poids total.
    """
    if not load:
        return True, "", 0.0, 0.0
    qty_by_container: dict[str, int] = {}
    total_weight = 0.0
    for flow in load:
        cont = containers[flow.container_type]
        qty_by_container[flow.container_type] = qty_by_container.get(flow.container_type, 0) + flow.quantity
        total_weight += container_weight_for_flow(cont, flow) * flow.quantity
    if total_weight - vehicle.max_weight_t > 1e-9:
        return False, f"Poids chargé {total_weight:.2f}T > capacité {vehicle.max_weight_t:.2f}T", 0.0, total_weight
    surface_sum = 0.0
    for cont_name, qty in qty_by_container.items():
        cont = containers[cont_name]
        frac = surface_fraction(vehicle, cont, qty)
        if frac > 1 + 1e-9:
            return False, f"Capacité discrète dépassée pour {cont_name}: {qty} contenants", frac * 100, total_weight
        surface_sum += frac
    # Modèle conservateur : pour les chargements mixtes, la somme des fractions ne doit pas dépasser 100%.
    if surface_sum > 1 + 1e-9:
        return False, f"Surface de plancher estimée dépassée: {surface_sum:.0%}", surface_sum * 100, total_weight
    return True, "", surface_sum * 100, total_weight
