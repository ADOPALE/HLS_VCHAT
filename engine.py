"""Orchestration d'une simulation OptiFLUX complète par jour."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from data_loader import OptiFluxData
from dock_scheduler import build_dock_planning
from driver_scheduler import schedule_driver_posts
from exceptions import InfeasibleProblemError
from models import DayResult, Flow
from optimizer import Optimizer
from preprocessing import active_flows_for_day
from route_builder import routes_to_steps
from time_windows import check_theoretical_feasibility, minutes_to_hhmm
from validators import validate_solution


def simulate_day(
    data: OptiFluxData,
    day: str,
    functions: list[str] | None = None,
    traffic_factor_pct: float = 0.0,
    progress_callback: Callable[[float, str], None] | None = None,
) -> DayResult:
    """Exécute contrôles, optimisation, planification et indicateurs pour un jour."""
    flows = active_flows_for_day(data, day, functions)
    feasibility_errors = check_theoretical_feasibility(data, flows, traffic_factor_pct)
    blocking = [d for d in feasibility_errors if d.severity == "CRITIQUE"]
    if blocking:
        raise InfeasibleProblemError(blocking)
    optimizer = Optimizer(data, day, traffic_factor_pct=traffic_factor_pct, progress_callback=progress_callback)
    routes = optimizer.optimize(flows)
    steps = routes_to_steps(data, day, routes, traffic_factor_pct)
    posts, scheduled_steps = schedule_driver_posts(data, day, routes, steps)
    dock_rows, dock_controls = build_dock_planning(data, day, scheduled_steps)
    transported_rows = build_transported_flows(day, flows, routes)
    served_keys = {row["ID flux"] for row in transported_rows}
    unserved = [
        {"Jour": day, "ID flux": f.object_key, "Origine": f.origin, "Destination": f.destination, "Raison de non-traitement": "Non affecté", "Contrainte bloquante": "FLUX_NON_SERVI"}
        for f in flows if f.object_key not in served_keys
    ]
    indicators = build_indicators(data, day, flows, routes, posts, unserved)
    result = DayResult(day=day, routes=routes, steps=scheduled_steps, posts=posts, dock_planning=dock_rows, transported_flows=transported_rows, unserved_flows=unserved, controls=dock_controls, indicators=indicators)
    result.controls = validate_solution(result)
    return result


def build_transported_flows(day: str, flows: list[Flow], routes) -> list[dict]:
    rows = []
    pickup_times: dict[str, int] = {}
    delivery_times: dict[str, int] = {}
    vehicle_by_flow: dict[str, tuple[str, str]] = {}
    for route in routes:
        for visit in route.visites:
            for f in visit.flux_charges:
                pickup_times[f.object_key] = max(route.scheduled_start or f.ready_time, f.ready_time)
                vehicle_by_flow[f.object_key] = (route.vehicle.type, route.route_id)
            for f in visit.flux_decharges:
                delivery_times[f.object_key] = min(route.scheduled_end or f.due_time, f.due_time)
    for route in routes:
        for f in route.flux:
            rows.append({
                "Jour": day,
                "ID flux": f.object_key,
                "Origine": f.origin,
                "Destination": f.destination,
                "Fonction support": f.function,
                "Type contenant": f.container_type,
                "Nb contenants": f.quantity,
                "Véhicule": route.vehicle.type,
                "N° tournée": route.route_id,
                "Heure collecte": minutes_to_hhmm(pickup_times.get(f.object_key, f.ready_time)),
                "Heure livraison": minutes_to_hhmm(delivery_times.get(f.object_key, f.due_time)),
                "Conformité horaire (O/N)": "O",
            })
    return rows


def build_indicators(data: OptiFluxData, day: str, flows: list[Flow], routes, posts, unserved) -> dict:
    km_total = sum(r.distance_km for r in routes)
    km_loaded = sum(r.loaded_km for r in routes)
    km_empty = sum(r.empty_km for r in routes)
    total_containers = sum(f.quantity for f in flows)
    served_count = len(flows) - len(unserved)
    return {
        "Jour": day,
        "Nb total de flux": len(flows),
        "Nb total de contenants": total_containers,
        "Nb flux servis": served_count,
        "Taux de service (%)": round(served_count / max(1, len(flows)) * 100, 1),
        "Km totaux": round(km_total, 2),
        "Km à plein": round(km_loaded, 2),
        "Km à vide": round(km_empty, 2),
        "Taux km à vide (%)": round(km_empty / max(0.001, km_total) * 100, 1),
        "Nb véhicules (= véhicules physiques utilisés)": len({p.vehicle_instance for p in posts}),
        "Nb postes chauffeurs": len(posts),
        "Nb désinfections": sum(p.disinfections for p in posts),
        "vacation_duration": data.rh.vacation_duration,
        "pause_duration": data.rh.pause_duration,
        "heure_fin_max": data.rh.end_max,
    }
