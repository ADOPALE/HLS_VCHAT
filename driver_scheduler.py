"""Affectation des circuits à des postes chauffeurs et véhicules physiques."""

from __future__ import annotations

from collections import defaultdict

from config import DISINFECTION_MIN, END_OF_SHIFT_MIN, PICKUP_PREP_MIN
from data_loader import OptiFluxData
from models import DriverPost, RoutePDTW, StepOperation


def schedule_driver_posts(data: OptiFluxData, day: str, routes: list[RoutePDTW], steps: list[StepOperation]) -> tuple[list[DriverPost], list[StepOperation]]:
    """Crée un poste chauffeur exact par circuit et groupe les circuits compatibles sur véhicules physiques."""
    steps_by_route: dict[str, list[StepOperation]] = defaultdict(list)
    for step in steps:
        steps_by_route[step.route_id].append(step)

    vehicle_instances: dict[str, list[tuple[int, int, str, bool]]] = defaultdict(list)
    posts: list[DriverPost] = []
    updated_steps: list[StepOperation] = []

    routes_sorted = sorted(routes, key=lambda r: ((r.scheduled_start or 0), r.vehicle.type, r.route_id))
    counters: dict[str, int] = defaultdict(int)
    post_counter = 1

    for route in routes_sorted:
        route_start = route.scheduled_start or data.rh.start_min
        # Poste exact de durée vacation. Il démarre avant la tournée pour intégrer la prise de poste.
        post_start = max(data.rh.start_min, route_start - PICKUP_PREP_MIN)
        if post_start + data.rh.vacation_duration > data.rh.end_max:
            post_start = data.rh.end_max - data.rh.vacation_duration
        route_shift = route_start - (post_start + PICKUP_PREP_MIN)
        # Si on a reculé le poste, on recale les steps route en conservant leur ordre.
        r_steps = [s.model_copy() for s in steps_by_route[route.route_id]]
        if route_shift != 0:
            for s in r_steps:
                s.start_min -= route_shift
                s.end_min -= route_shift

        post_end = post_start + data.rh.vacation_duration
        route_end = max(s.end_min for s in r_steps) if r_steps else post_start + PICKUP_PREP_MIN
        has_dirty = route.has_dirty
        instance = _pick_vehicle_instance(vehicle_instances, counters, route.vehicle.type, post_start, post_end, has_dirty)
        post_id = f"P{post_counter:03d}"
        post_counter += 1

        # Ajoute prise de poste, pause, fin de poste et inoccupé.
        enriched: list[StepOperation] = []
        enriched.append(StepOperation(day=day, route_id=route.route_id, post_id=post_id, vehicle_instance=instance, vehicle_type=route.vehicle.type, order=0, start_min=post_start, end_min=post_start + PICKUP_PREP_MIN, operation="Prise de poste", site=route.vehicle.initial_site, duration_min=PICKUP_PREP_MIN, sanitary_state="Propre"))
        for s in r_steps:
            s.post_id = post_id
            s.vehicle_instance = instance
            enriched.append(s)
        pause_mid = post_start + data.rh.vacation_duration // 2 - data.rh.pause_duration // 2
        # Pause au dépôt : si la tournée finit avant le milieu, la pause se place au milieu ; sinon après retour dépôt si possible.
        pause_start = max(pause_mid, route_end)
        if pause_start + data.rh.pause_duration > post_end - END_OF_SHIFT_MIN:
            pause_start = max(post_start + PICKUP_PREP_MIN, post_end - END_OF_SHIFT_MIN - data.rh.pause_duration)
        enriched.append(StepOperation(day=day, route_id=route.route_id, post_id=post_id, vehicle_instance=instance, vehicle_type=route.vehicle.type, order=998, start_min=pause_start, end_min=pause_start + data.rh.pause_duration, operation="Pause", site=route.vehicle.initial_site, duration_min=data.rh.pause_duration, sanitary_state="Propre" if not has_dirty else "Sale"))
        enriched.append(StepOperation(day=day, route_id=route.route_id, post_id=post_id, vehicle_instance=instance, vehicle_type=route.vehicle.type, order=999, start_min=post_end - END_OF_SHIFT_MIN, end_min=post_end, operation="Fin de poste", site=route.vehicle.initial_site, duration_min=END_OF_SHIFT_MIN, sanitary_state="Propre" if not has_dirty else "Sale"))
        enriched.sort(key=lambda s: (s.start_min, s.order))
        for idx, s in enumerate(enriched, start=1):
            s.order = idx
        updated_steps.extend(enriched)

        conduite = sum(s.duration_min for s in enriched if "Trajet" in s.operation or "Retour" in s.operation)
        quai = sum(s.duration_min for s in enriched if "Quai" in s.operation)
        manut = quai
        attente = max(0, data.rh.vacation_duration - sum(s.duration_min for s in enriched if s.operation not in {"Temps inoccupé"}))
        post = DriverPost(day=day, post_id=post_id, vehicle_instance=instance, vehicle_type=route.vehicle.type, route_id=route.route_id, start_min=post_start, end_min=post_end, steps=enriched, disinfections=0, conduite_min=conduite, manutention_min=manut, quai_min=quai, attente_min=attente, inoccuped_min=attente)
        posts.append(post)
        vehicle_instances[route.vehicle.type].append((post_start, post_end, instance, has_dirty))

    return posts, updated_steps


def _pick_vehicle_instance(vehicle_instances, counters, vehicle_type: str, start: int, end: int, has_dirty: bool) -> str:
    for _, busy in vehicle_instances.items():
        pass
    candidates = vehicle_instances[vehicle_type]
    for s, e, instance, prev_dirty in candidates:
        # même véhicule physique si pas de chevauchement. Désinfection gérée comme contrainte temporelle simplifiée.
        if e + (DISINFECTION_MIN if prev_dirty else 0) <= start or end <= s:
            return instance
    counters[vehicle_type] += 1
    return f"{vehicle_type} #{counters[vehicle_type]}"
