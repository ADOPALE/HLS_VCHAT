"""Conversion des routes VRPPDTW en étapes opérationnelles détaillées."""

from __future__ import annotations

from collections import defaultdict

from capacity import load_ok
from config import CLEAN_VALUE, DIRTY_VALUE
from data_loader import OptiFluxData
from models import Flow, RoutePDTW, StepOperation
from time_windows import distance_km, travel_time


def _summarize(flows: list[Flow]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for f in flows:
        out[f.container_type] += f.quantity
    return dict(out)


def route_to_steps(data: OptiFluxData, day: str, route: RoutePDTW, traffic_factor_pct: float = 0.0) -> list[StepOperation]:
    """Transforme une route en timeline opérationnelle chronologique."""
    steps: list[StepOperation] = []
    depot = route.vehicle.initial_site
    current_site = depot
    current_time = route.scheduled_start or data.rh.start_min
    load: list[Flow] = []
    sanitary_state = "Propre"
    order = 1

    for visit in route.visites:
        leg_duration = int(round(travel_time(data, current_site, visit.site, traffic_factor_pct)))
        leg_dist = distance_km(data, current_site, visit.site)
        if leg_duration > 0 or current_site != visit.site:
            steps.append(
                StepOperation(
                    day=day,
                    route_id=route.route_id,
                    vehicle_type=route.vehicle.type,
                    order=order,
                    start_min=current_time,
                    end_min=current_time + leg_duration,
                    operation="Trajet chargé" if load else "Trajet à vide",
                    site_from=current_site,
                    site_to=visit.site,
                    flux_keys=[f.object_key for f in load],
                    distance_km=leg_dist,
                    duration_min=leg_duration,
                    sanitary_state=sanitary_state,
                    empty_leg=not bool(load),
                )
            )
            current_time += leg_duration
            order += 1
        current_site = visit.site

        if visit.flux_charges:
            current_time = max(current_time, max(f.ready_time for f in visit.flux_charges))
        site = data.sites[visit.site]
        all_ops = visit.flux_charges + visit.flux_decharges
        if all_ops:
            per = route.vehicle.manual_dock_min_per_container if site.has_dock else route.vehicle.manual_no_dock_min_per_container
            per = per or 0.0
            duration = int(round(route.vehicle.dock_time_min + per * sum(f.quantity for f in all_ops)))
            before_load = list(load)
            for f in visit.flux_decharges:
                if f in load:
                    load.remove(f)
            load.extend(visit.flux_charges)
            if any(str(f.clean_dirty).strip().casefold() == DIRTY_VALUE for f in before_load + visit.flux_charges):
                sanitary_state = "Sale"
            ok, _, fill_pct, _ = load_ok(route.vehicle, data.containers, load)
            steps.append(
                StepOperation(
                    day=day,
                    route_id=route.route_id,
                    vehicle_type=route.vehicle.type,
                    order=order,
                    start_min=current_time,
                    end_min=current_time + duration,
                    operation="Quai + manutention",
                    site=visit.site,
                    flux_keys=[f.object_key for f in all_ops],
                    loaded_containers=_summarize(visit.flux_charges),
                    unloaded_containers=_summarize(visit.flux_decharges),
                    fill_rate_surface_pct=round(fill_pct, 1),
                    duration_min=duration,
                    sanitary_state=sanitary_state,
                    comment=None if ok else "Attention capacité recalculée non conforme",
                )
            )
            current_time += duration
            order += 1

    leg_duration = int(round(travel_time(data, current_site, depot, traffic_factor_pct)))
    leg_dist = distance_km(data, current_site, depot)
    steps.append(
        StepOperation(
            day=day,
            route_id=route.route_id,
            vehicle_type=route.vehicle.type,
            order=order,
            start_min=current_time,
            end_min=current_time + leg_duration,
            operation="Retour dépôt chargé" if load else "Retour dépôt à vide",
            site_from=current_site,
            site_to=depot,
            flux_keys=[f.object_key for f in load],
            distance_km=leg_dist,
            duration_min=leg_duration,
            sanitary_state=sanitary_state,
            empty_leg=not bool(load),
        )
    )
    return steps


def routes_to_steps(data: OptiFluxData, day: str, routes: list[RoutePDTW], traffic_factor_pct: float = 0.0) -> list[StepOperation]:
    all_steps: list[StepOperation] = []
    for route in routes:
        all_steps.extend(route_to_steps(data, day, route, traffic_factor_pct))
    return all_steps
