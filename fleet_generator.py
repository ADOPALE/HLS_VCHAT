"""Génération et comparaison de configurations de flotte.

Le moteur principal utilise une affectation progressive des véhicules, mais ce
module fournit des fonctions de support pour tester des scénarios de flotte plus
probables avant d'élargir la recherche.
"""

from __future__ import annotations

import itertools
from collections import defaultdict

from capacity import max_containers_for_flow
from compatibility import compatible_vehicles_for_flow
from data_loader import OptiFluxData
from models import Flow


def theoretical_peak_by_vehicle(data: OptiFluxData, flows: list[Flow]) -> dict[str, int]:
    """Estime un besoin minimal par type de véhicule à partir du volume total compatible."""
    need: dict[str, int] = defaultdict(int)
    for flow in flows:
        vehicles = compatible_vehicles_for_flow(flow, data.vehicles, data.sites)
        if not vehicles:
            continue
        best = max(vehicles, key=lambda v: max_containers_for_flow(v, data.containers[flow.container_type], flow))
        cap = max(1, max_containers_for_flow(best, data.containers[flow.container_type], flow))
        need[best.type] += (flow.quantity + cap - 1) // cap
    return dict(need)


def enumerate_probable_fleet_scenarios(data: OptiFluxData, flows: list[Flow], max_extra: int = 3) -> list[dict[str, int]]:
    """Énumère des scénarios de flotte autour du besoin théorique, plutôt que tous les scénarios possibles."""
    base = theoretical_peak_by_vehicle(data, flows)
    vehicle_types = list(data.vehicles.keys())
    scenarios: list[dict[str, int]] = []
    ranges = []
    for vt in vehicle_types:
        b = base.get(vt, 0)
        max_allowed = data.vehicles[vt].max_instances or max(b + max_extra, max_extra)
        ranges.append(range(0, max_allowed + 1))
    for values in itertools.product(*ranges):
        s = dict(zip(vehicle_types, values))
        if sum(s.values()) == 0:
            continue
        if all(s.get(vt, 0) >= base.get(vt, 0) for vt in base):
            scenarios.append(s)
    scenarios.sort(key=lambda x: (sum(x.values()), sum(data.vehicles[vt].floor_area_m2 * n for vt, n in x.items())))
    return scenarios
