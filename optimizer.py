"""Moteur VRPPDTW hybride OptiFLUX.

Le moteur construit des routes pickup & delivery avec fenêtres temporelles par
insertion constructive, puis améliore localement la solution. L'objectif est la
meilleure solution opérationnelle valide dans un budget temps donné. Les
contraintes dures sont systématiquement revérifiées après chaque insertion.
"""

from __future__ import annotations

import itertools
import time
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable

from capacity import load_ok, max_containers_for_flow
from compatibility import compatible_vehicles_for_flow, simultaneous_load_sanitary_compatible, vehicle_state_can_load, vehicle_compatible_with_flow
from config import CLEAN_VALUE, DEFAULT_OPTIM_TIME_LIMIT_SEC, DIRTY_VALUE, DISINFECTION_MIN, EPS, MAX_GAP_HORAIRE_CIRCUIT
from data_loader import OptiFluxData
from exceptions import Diagnostic, InfeasibleProblemError, OptimizationError
from models import Flow, RoutePDTW, VehicleType, VisiteSite
from preprocessing import group_by_mutualized_name, split_oversized_flows, validate_flow_references
from time_windows import distance_km, travel_time

ProgressCallback = Callable[[float, str], None]


@dataclass
class RouteEval:
    feasible: bool
    reason: str = ""
    start_min: int | None = None
    end_min: int | None = None
    duration_min: int = 0
    distance_km: float = 0.0
    loaded_km: float = 0.0
    empty_km: float = 0.0


class Optimizer:
    def __init__(
        self,
        data: OptiFluxData,
        day: str,
        traffic_factor_pct: float = 0.0,
        max_gap_horaire_circuit: int = MAX_GAP_HORAIRE_CIRCUIT,
        time_limit_sec: int = DEFAULT_OPTIM_TIME_LIMIT_SEC,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.data = data
        self.day = day
        self.traffic_factor_pct = traffic_factor_pct
        self.max_gap = max_gap_horaire_circuit
        self.time_limit_sec = time_limit_sec
        self.progress_callback = progress_callback or (lambda pct, msg: None)
        self.start_wall = time.time()
        self.route_seq = 1

    def _deadline_exceeded(self) -> bool:
        return time.time() - self.start_wall > self.time_limit_sec

    def optimize(self, base_flows: list[Flow]) -> list[RoutePDTW]:
        """Produit des routes valides couvrant 100% des flux actifs."""
        diagnostics = validate_flow_references(self.data, base_flows)
        blocking = [d for d in diagnostics if d.severity == "CRITIQUE"]
        if blocking:
            raise InfeasibleProblemError(blocking)

        split_flows = split_oversized_flows(base_flows, self.max_capacity_any_vehicle)
        groups = group_by_mutualized_name(split_flows)
        groups.sort(key=self._group_priority_key)

        routes: list[RoutePDTW] = []
        total = max(1, len(groups))
        for i, group in enumerate(groups, start=1):
            self.progress_callback(min(0.85, i / total * 0.85), f"Insertion des flux {i}/{total}")
            if self._deadline_exceeded():
                break
            inserted = self._insert_group_in_existing_routes(routes, group)
            if not inserted:
                route = self._create_best_route_for_group(group)
                routes.append(route)

        self.progress_callback(0.9, "Amélioration locale des tournées")
        routes = self.local_search(routes)
        self.progress_callback(0.96, "Validation finale des tournées")
        self._assert_all_flows_served(split_flows, routes)
        return routes

    def max_capacity_any_vehicle(self, flow: Flow) -> int:
        caps = []
        for vehicle in compatible_vehicles_for_flow(flow, self.data.vehicles, self.data.sites):
            caps.append(max_containers_for_flow(vehicle, self.data.containers[flow.container_type], flow))
        return max(caps) if caps else 0

    def _group_priority_key(self, group: list[Flow]) -> tuple:
        ready = min(f.ready_time for f in group)
        due = min(f.due_time for f in group)
        qty = sum(f.quantity for f in group)
        priority = max(1 if f.priority else 0 for f in group)
        mutualized = 0 if any(f.mutualized_name for f in group) else 1
        return (-priority, mutualized, due, ready, -qty)

    def _insert_group_in_existing_routes(self, routes: list[RoutePDTW], group: list[Flow]) -> bool:
        candidates: list[tuple[float, RoutePDTW]] = []
        for route in routes:
            if all(vehicle_compatible_with_flow(route.vehicle, f, self.data.sites)[0] for f in group):
                # La compatibilité sanitaire dépend de l'ordre réel des chargements/déchargements.
                # Elle est donc contrôlée dans evaluate_route(), et non par simple présence
                # de flux propres et sales dans la même tournée.
                candidates.append((self._incremental_distance_hint(route, group), route))
        candidates.sort(key=lambda x: x[0])
        for _, route in candidates:
            clone = route.clone()
            success = True
            for flow in group:
                if not self._insert_single_flow_best(clone, flow):
                    success = False
                    break
            if success:
                route.visites = clone.visites
                ev = self.evaluate_route(route)
                self._apply_eval(route, ev)
                return True
        return False

    def _create_best_route_for_group(self, group: list[Flow]) -> RoutePDTW:
        vehicles = list(self.data.vehicles.values())
        feasible_vehicles: list[VehicleType] = []
        for vehicle in vehicles:
            if all(vehicle_compatible_with_flow(vehicle, f, self.data.sites)[0] for f in group):
                feasible_vehicles.append(vehicle)
        if not feasible_vehicles:
            reasons = []
            for vehicle in vehicles:
                for flow in group:
                    ok, reason = vehicle_compatible_with_flow(vehicle, flow, self.data.sites)
                    if not ok:
                        reasons.append(f"{vehicle.type}/{flow.object_key}: {reason}")
                        break
            raise InfeasibleProblemError([Diagnostic("M flux", group[0].row_excel, None, "CRITIQUE", "AUCUN_VEHICULE_GROUPE", "Impossible de trouver un véhicule compatible avec un groupe de flux. " + " | ".join(reasons[:10]))])

        feasible_vehicles.sort(key=lambda v: (v.floor_area_m2, v.max_weight_t, v.fuel_cost_per_km, v.type))
        best_route: RoutePDTW | None = None
        best_cost = float("inf")
        vehicle_failures: list[str] = []
        for vehicle in feasible_vehicles:
            route = RoutePDTW(route_id=f"R{self.route_seq:04d}", vehicle=vehicle)
            ok = True
            failed_flow: Flow | None = None
            for flow in group:
                if not self._insert_single_flow_best(route, flow):
                    ok = False
                    failed_flow = flow
                    break
            if ok:
                ev = self.evaluate_route(route)
                if ev.feasible:
                    # Coût lexicographique implicite : petite flotte déjà par insertion ; ici on évite les véhicules trop grands et les km.
                    cost = ev.distance_km + vehicle.floor_area_m2 * 0.01 + vehicle.fuel_cost_per_km * 0.1
                    if cost < best_cost:
                        best_cost = cost
                        best_route = route.clone()
                        self._apply_eval(best_route, ev)
                else:
                    vehicle_failures.append(f"{vehicle.type}: {ev.reason}")
            else:
                detail = self._diagnose_failed_insertion(vehicle, group, failed_flow)
                vehicle_failures.append(f"{vehicle.type}: impossible d'insérer {failed_flow.object_key if failed_flow else 'un flux'} ({detail})")
        if best_route is None:
            msg = "; ".join(f.object_key for f in group)
            detail = " | ".join(vehicle_failures[:8])
            raise InfeasibleProblemError([Diagnostic("M flux", group[0].row_excel, None, "CRITIQUE", "INSERTION_IMPOSSIBLE", f"Impossible de construire une tournée valide pour le groupe : {msg}. Véhicules compatibles testés mais non retenus : {detail}")])
        self.route_seq += 1
        return best_route


    def _diagnose_failed_insertion(self, vehicle: VehicleType, group: list[Flow], failed_flow: Flow | None) -> str:
        """Fournit une explication métier courte quand un véhicule compatible ne permet pas d'insérer tout un groupe."""
        if failed_flow is None:
            return "contrainte non identifiée"
        container = self.data.containers[failed_flow.container_type]
        cap = max_containers_for_flow(vehicle, container, failed_flow)
        same_origin_ready = [
            f for f in group
            if f is not failed_flow
            and f.origin == failed_flow.origin
            and f.container_type == failed_flow.container_type
            and abs(f.ready_time - failed_flow.ready_time) <= EPS
        ]
        if same_origin_ready:
            total_qty = failed_flow.quantity + sum(f.quantity for f in same_origin_ready)
            if total_qty > cap:
                return (
                    f"capacité instantanée insuffisante si co-chargement depuis {failed_flow.origin}: "
                    f"{total_qty} {failed_flow.container_type} à charger, capacité {cap} pour {vehicle.type}. "
                    "Un retour au point d'origine entre deux livraisons peut aussi être incompatible avec les fenêtres horaires."
                )
        window = failed_flow.due_time - failed_flow.ready_time
        return f"fenêtre {window} min, contraintes de capacité / ordre pickup-delivery / horaires trop fortes pour ce groupe mutualisé"

    def _insert_single_flow_best(self, route: RoutePDTW, flow: Flow) -> bool:
        best: tuple[float, list[VisiteSite], RouteEval] | None = None
        current_dist = self.evaluate_route(route).distance_km if route.visites else 0.0
        n = len(route.visites)
        pickup_options = [("new", i) for i in range(n + 1)] + [("existing", i) for i, v in enumerate(route.visites) if v.site == flow.origin]
        for p_mode, p_idx in pickup_options:
            if p_mode == "new":
                delivery_indices = range(p_idx, n + 1)
            else:
                delivery_indices = range(p_idx + 1, n + 1)
            for d_idx in delivery_indices:
                # Livraison dans visite existante du site destination si possible, sinon nouvelle visite.
                delivery_modes = ["new"]
                effective_n = n + (1 if p_mode == "new" else 0)
                for j in range(effective_n):
                    # les indices effectifs sont reconstruits dans _apply_insertion ; option existante uniquement si le site correspond.
                    pass
                candidates = [("new", d_idx)]
                # Ajout des visites existantes destination après pickup.
                for j, visit in enumerate(route.visites):
                    min_j = p_idx + 1 if p_mode == "existing" else p_idx
                    if visit.site == flow.destination and j >= min_j:
                        candidates.append(("existing", j))
                for d_mode, d_raw_idx in candidates:
                    try:
                        new_visites = self._apply_insertion(route.visites, flow, p_mode, p_idx, d_mode, d_raw_idx)
                    except ValueError:
                        continue
                    test = route.clone()
                    test.visites = new_visites
                    ev = self.evaluate_route(test)
                    if not ev.feasible:
                        continue
                    extra = ev.distance_km - current_dist
                    if best is None or extra < best[0] - EPS:
                        best = (extra, new_visites, ev)
        if best is None:
            return False
        _, visites, ev = best
        route.visites = visites
        self._apply_eval(route, ev)
        return True

    def _apply_insertion(
        self,
        visites: list[VisiteSite],
        flow: Flow,
        pickup_mode: str,
        pickup_idx: int,
        delivery_mode: str,
        delivery_idx: int,
    ) -> list[VisiteSite]:
        new = [v.clone() for v in visites]
        if pickup_mode == "new":
            if pickup_idx < 0 or pickup_idx > len(new):
                raise ValueError("pickup_idx invalide")
            new.insert(pickup_idx, VisiteSite(site=flow.origin, flux_charges=[flow]))
            if delivery_idx >= pickup_idx:
                delivery_idx += 1
        else:
            if pickup_idx < 0 or pickup_idx >= len(new) or new[pickup_idx].site != flow.origin:
                raise ValueError("pickup existant invalide")
            new[pickup_idx].flux_charges.append(flow)
            if delivery_idx <= pickup_idx:
                raise ValueError("delivery doit être après pickup")

        if delivery_mode == "new":
            if delivery_idx < 0 or delivery_idx > len(new):
                raise ValueError("delivery_idx invalide")
            new.insert(delivery_idx, VisiteSite(site=flow.destination, flux_decharges=[flow]))
        else:
            if delivery_idx < 0 or delivery_idx >= len(new) or new[delivery_idx].site != flow.destination:
                raise ValueError("delivery existante invalide")
            if delivery_idx <= pickup_idx:
                raise ValueError("delivery existante doit être après pickup")
            new[delivery_idx].flux_decharges.append(flow)
        return [v for v in new if not v.is_empty()]

    def evaluate_route(self, route: RoutePDTW) -> RouteEval:
        if not route.visites:
            return RouteEval(True, start_min=self.data.rh.start_min, end_min=self.data.rh.start_min, duration_min=0)
        all_flows = route.flux
        ready_times = [f.ready_time for f in all_flows]
        if max(ready_times) - min(ready_times) > self.max_gap:
            return RouteEval(False, f"Écart entre heures de disponibilité > {self.max_gap} min")
        ok, reason = self._respecte_ordre_pd(route)
        if not ok:
            return RouteEval(False, reason)

        depot = route.vehicle.initial_site
        # Départ au plus tard possible avant le premier pickup pour limiter l'attente, sans dépasser début mini.
        first_site = route.visites[0].site
        travel_to_first = travel_time(self.data, depot, first_site, self.traffic_factor_pct)
        earliest_pickup = min(f.ready_time for f in all_flows)
        depart = max(self.data.rh.start_min, int(round(earliest_pickup - travel_to_first)))
        current_time = float(depart)
        current_site = depot
        distance = loaded_km = empty_km = 0.0
        load: list[Flow] = []

        for visit in route.visites:
            leg_dist = distance_km(self.data, current_site, visit.site)
            distance += leg_dist
            if load:
                loaded_km += leg_dist
            else:
                empty_km += leg_dist
            current_time += travel_time(self.data, current_site, visit.site, self.traffic_factor_pct)
            current_site = visit.site

            # Livraisons d'abord pour libérer la capacité, sauf si un même flux serait déchargé avant chargement.
            for f in visit.flux_decharges:
                if f not in load:
                    return RouteEval(False, f"Déchargement avant chargement pour {f.object_key}")
            if visit.flux_charges:
                current_time = max(current_time, max(f.ready_time for f in visit.flux_charges))
            site = self.data.sites[visit.site]
            qty_ops = sum(f.quantity for f in visit.flux_charges + visit.flux_decharges)
            if qty_ops > 0:
                per = route.vehicle.manual_dock_min_per_container if site.has_dock else route.vehicle.manual_no_dock_min_per_container
                if per is None:
                    return RouteEval(False, f"Manutention impossible sans quai sur {visit.site}")
                current_time += route.vehicle.dock_time_min + per * qty_ops

            # décharge
            for f in visit.flux_decharges:
                if current_time - f.due_time > EPS:
                    return RouteEval(False, f"Livraison hors délai pour {f.object_key}: {current_time:.0f} > {f.due_time}")
                load.remove(f)
            # charge
            load.extend(visit.flux_charges)
            sanitary_ok, sanitary_reason = simultaneous_load_sanitary_compatible(load)
            if not sanitary_ok:
                return RouteEval(False, sanitary_reason)
            cap_ok, cap_reason, _, _ = load_ok(route.vehicle, self.data.containers, load)
            if not cap_ok:
                return RouteEval(False, cap_reason)

        leg_dist = distance_km(self.data, current_site, depot)
        distance += leg_dist
        if load:
            loaded_km += leg_dist
        else:
            empty_km += leg_dist
        current_time += travel_time(self.data, current_site, depot, self.traffic_factor_pct)
        if load:
            return RouteEval(False, "Retour au dépôt avec chargement non livré")

        duration = int(round(current_time - depart))
        max_useful = self.data.rh.useful_one_shift_duration
        if duration > max_useful + EPS:
            return RouteEval(False, f"Circuit {duration} min > budget utile d'un poste {max_useful} min")
        if current_time > self.data.rh.end_max - 10 + EPS:
            return RouteEval(False, "Circuit finit trop tard pour la fin de poste")
        return RouteEval(True, start_min=depart, end_min=int(round(current_time)), duration_min=duration, distance_km=distance, loaded_km=loaded_km, empty_km=empty_km)

    def _respecte_ordre_pd(self, route: RoutePDTW) -> tuple[bool, str]:
        seen: set[str] = set()
        delivered: set[str] = set()
        for idx, visit in enumerate(route.visites):
            for f in visit.flux_decharges:
                if f.object_key not in seen:
                    return False, f"Déchargement avant chargement {f.object_key} à la visite {idx}"
                delivered.add(f.object_key)
            for f in visit.flux_charges:
                seen.add(f.object_key)
        missing = seen - delivered
        if missing:
            return False, f"Flux chargés non livrés : {sorted(missing)[:5]}"
        return True, ""

    def _apply_eval(self, route: RoutePDTW, ev: RouteEval) -> None:
        route.scheduled_start = ev.start_min
        route.scheduled_end = ev.end_min
        route.duration_min = ev.duration_min
        route.distance_km = ev.distance_km
        route.loaded_km = ev.loaded_km
        route.empty_km = ev.empty_km
        route.feasible = ev.feasible
        route.infeasibility_reason = ev.reason or None

    def _incremental_distance_hint(self, route: RoutePDTW, group: list[Flow]) -> float:
        if not route.visites:
            return 0.0
        sites = [v.site for v in route.visites]
        add = 0.0
        for flow in group:
            best = min(distance_km(self.data, s, flow.origin) + distance_km(self.data, flow.destination, s) for s in sites)
            add += best
        return add

    def local_search(self, routes: list[RoutePDTW]) -> list[RoutePDTW]:
        improved = True
        while improved and not self._deadline_exceeded():
            improved = self._or_opt_once(routes)
        return [r for r in routes if r.visites]

    def _or_opt_once(self, routes: list[RoutePDTW]) -> bool:
        for src in list(routes):
            split_counts = Counter(f.id_flux for f in src.flux if f.is_split)
            movable = [f for f in src.flux if split_counts.get(f.id_flux, 0) <= 1]
            for flow in movable:
                for dst in routes:
                    if src is dst:
                        continue
                    if not vehicle_compatible_with_flow(dst.vehicle, flow, self.data.sites)[0]:
                        continue
                    src_test = self._remove_flow(src, flow)
                    dst_test = dst.clone()
                    if not self._insert_single_flow_best(dst_test, flow):
                        continue
                    ev_src = self.evaluate_route(src_test)
                    ev_dst = self.evaluate_route(dst_test)
                    if not ev_src.feasible or not ev_dst.feasible:
                        continue
                    before = src.distance_km + dst.distance_km
                    after = ev_src.distance_km + ev_dst.distance_km
                    if after + EPS < before:
                        src.visites = src_test.visites
                        self._apply_eval(src, ev_src)
                        dst.visites = dst_test.visites
                        self._apply_eval(dst, ev_dst)
                        return True
        return False

    def _remove_flow(self, route: RoutePDTW, flow: Flow) -> RoutePDTW:
        clone = route.clone()
        for visit in clone.visites:
            visit.flux_charges = [f for f in visit.flux_charges if f.object_key != flow.object_key]
            visit.flux_decharges = [f for f in visit.flux_decharges if f.object_key != flow.object_key]
        clone.visites = [v for v in clone.visites if not v.is_empty()]
        return clone

    def _assert_all_flows_served(self, flows: list[Flow], routes: list[RoutePDTW]) -> None:
        expected = {f.object_key for f in flows}
        served = {f.object_key for r in routes for f in r.flux}
        missing = expected - served
        if missing:
            raise OptimizationError(f"Flux non servis après optimisation : {sorted(missing)[:10]}")
