"""Fenêtres horaires, calculs de faisabilité théorique et formatage."""

from __future__ import annotations

import math

from capacity import max_containers_for_flow
from compatibility import compatible_vehicles_for_flow, vehicle_compatible_with_flow
from data_loader import OptiFluxData
from exceptions import Diagnostic, InfeasibleProblemError
from models import Flow, VehicleType


def minutes_to_hhmm(minutes: int | float | None) -> str:
    if minutes is None:
        return ""
    m = int(round(minutes))
    h = (m // 60) % 24
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def travel_time(data: OptiFluxData, origin: str, dest: str, traffic_factor_pct: float = 0.0) -> float:
    base = float(data.duration_matrix.get((origin, dest), 0.0))
    if abs(base) < 1e-9:
        return 0.0
    return base * (1 + traffic_factor_pct / 100.0)


def distance_km(data: OptiFluxData, origin: str, dest: str) -> float:
    return float(data.distance_matrix.get((origin, dest), 0.0))


def handling_time(vehicle: VehicleType, site_has_dock: bool, qty: int) -> float:
    per = vehicle.manual_dock_min_per_container if site_has_dock else vehicle.manual_no_dock_min_per_container
    if per is None:
        return float("inf")
    return vehicle.dock_time_min + per * qty


def t_min_for_flow(data: OptiFluxData, flow: Flow, vehicle: VehicleType, traffic_factor_pct: float = 0.0) -> tuple[float, str]:
    origin_site = data.sites[flow.origin]
    dest_site = data.sites[flow.destination]
    h1 = handling_time(vehicle, origin_site.has_dock, flow.quantity)
    h2 = handling_time(vehicle, dest_site.has_dock, flow.quantity)
    tr = travel_time(data, flow.origin, flow.destination, traffic_factor_pct)
    return h1 + tr + h2, f"mise quai/manutention départ {h1:.0f} + trajet {tr:.0f} + mise quai/manutention arrivée {h2:.0f}"


def check_theoretical_feasibility(data: OptiFluxData, flows: list[Flow], traffic_factor_pct: float = 0.0) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for flow in flows:
        compatible = compatible_vehicles_for_flow(flow, data.vehicles, data.sites)
        reasons: list[str] = []
        if not compatible:
            for vehicle in data.vehicles.values():
                ok, reason = vehicle_compatible_with_flow(vehicle, flow, data.sites)
                if not ok:
                    reasons.append(f"{vehicle.type}: {reason}")
            diagnostics.append(Diagnostic("M flux", flow.row_excel, None, "CRITIQUE", "AUCUN_VEHICULE_COMPATIBLE", f"Aucun véhicule compatible avec le flux {flow.object_key}. " + " | ".join(reasons[:5])))
            continue
        possible = False
        best_detail = None
        for vehicle in compatible:
            cap = max_containers_for_flow(vehicle, data.containers[flow.container_type], flow)
            if cap <= 0:
                reasons.append(f"{vehicle.type}: capacité nulle")
                continue
            tmin, detail = t_min_for_flow(data, flow, vehicle, traffic_factor_pct)
            window = flow.due_time - flow.ready_time
            if tmin <= window + 1e-9:
                possible = True
                break
            if best_detail is None or tmin < best_detail[0]:
                best_detail = (tmin, vehicle.type, detail, window)
        if not possible:
            if best_detail:
                tmin, vtype, detail, window = best_detail
                diagnostics.append(
                    Diagnostic(
                        "M flux",
                        flow.row_excel,
                        None,
                        "CRITIQUE",
                        "FENETRE_TROP_ETROITE",
                        f"Flux {flow.object_key} infaisable. Meilleur véhicule {vtype}: T_min={tmin:.0f} min, fenêtre={window:.0f} min, écart={tmin-window:.0f} min. Détail: {detail}",
                        "Élargir la fenêtre horaire, réduire la quantité ou modifier les compatibilités véhicule/site.",
                    )
                )
            else:
                diagnostics.append(Diagnostic("M flux", flow.row_excel, None, "CRITIQUE", "CAPACITE_NULLE", f"Aucun véhicule compatible n'a de capacité positive pour {flow.object_key}."))
    return diagnostics
