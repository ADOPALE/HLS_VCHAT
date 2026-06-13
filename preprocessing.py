"""Pré-traitement des flux : filtrage par jour, normalisation et éclatement."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from config import FREQUENCIES_VALUE, VOLUME_VALUE, WEEKDAYS, WEEKEND_DAYS
from data_loader import OptiFluxData, _ns, _quantity_to_int, _safe_str, _to_bool, _to_minutes, get_quantity_column
from exceptions import Diagnostic, InfeasibleProblemError
from models import Flow


def active_flows_for_day(data: OptiFluxData, day: str, functions: list[str] | None = None) -> list[Flow]:
    """Retourne les flux actifs Volume avec quantité > 0 pour le jour demandé."""
    if day not in WEEKDAYS:
        raise ValueError(f"Jour invalide : {day}")
    df = data.raw["M flux"].copy()
    cols = data.column_maps["M flux"]
    qty_col = get_quantity_column(df, day)
    selected_functions = set(functions or [])
    flows: list[Flow] = []

    for idx, row in df.iterrows():
        excel_row = int(idx) + 2
        nature = _safe_str(row.get(cols["flow_nature"]))
        if nature is None or _ns(nature) == _ns(FREQUENCIES_VALUE):
            continue
        if _ns(nature) != _ns(VOLUME_VALUE):
            continue
        qty = _quantity_to_int(row.get(qty_col))
        if qty <= 0:
            continue
        function = _safe_str(row.get(cols["flow_function"])) or "Non renseigné"
        if selected_functions and function not in selected_functions:
            continue

        ready = row.get(cols["flow_ready_time"])
        due = row.get(cols["flow_due_time"])
        if ready is None or due is None or (isinstance(ready, float) and math.isnan(ready)) or (isinstance(due, float) and math.isnan(due)):
            if day in WEEKEND_DAYS:
                ready = row.get(cols.get("flow_we_start"))
                due = row.get(cols.get("flow_we_end"))
            else:
                ready = row.get(cols.get("flow_week_start"))
                due = row.get(cols.get("flow_week_end"))
        ready_min = _to_minutes(ready, default=0, field="Heure de mise à disposition")
        due_min = _to_minutes(due, default=1439, field="Heure max de livraison")

        flows.append(
            Flow(
                row_excel=excel_row,
                id_flux=excel_row,
                origin=_safe_str(row.get(cols["flow_origin"])) or "",
                destination=_safe_str(row.get(cols["flow_destination"])) or "",
                function=function,
                label=_safe_str(row.get(cols.get("flow_label"))),
                container_type=_safe_str(row.get(cols["flow_container"])) or "",
                quantity=qty,
                original_quantity=qty,
                full_empty=_safe_str(row.get(cols["flow_full_empty"])) or "",
                clean_dirty=_safe_str(row.get(cols["flow_clean_dirty"])) or "",
                mixed_allowed=_to_bool(row.get(cols["flow_mixed_allowed"]), default=False),
                mixed_exclusion=_safe_str(row.get(cols["flow_mixed_exclusion"])),
                mutualized_name=_safe_str(row.get(cols["flow_mutualized_name"])),
                ready_time=ready_min,
                due_time=due_min,
                priority=_to_bool(row.get(cols.get("flow_priority")), default=False) if "flow_priority" in cols else False,
            )
        )
    return flows


def validate_flow_references(data: OptiFluxData, flows: Iterable[Flow]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    site_names = set(data.sites.keys())
    cont_names = set(data.containers.keys())
    for f in flows:
        if f.origin not in site_names:
            diagnostics.append(Diagnostic("M flux", f.row_excel, None, "CRITIQUE", "SITE_DEPART_INCONNU", f"Site de départ inconnu : {f.origin}"))
        if f.destination not in site_names:
            diagnostics.append(Diagnostic("M flux", f.row_excel, None, "CRITIQUE", "SITE_DESTINATION_INCONNU", f"Site de destination inconnu : {f.destination}"))
        if f.container_type not in cont_names:
            diagnostics.append(Diagnostic("M flux", f.row_excel, None, "CRITIQUE", "CONTENANT_INCONNU", f"Contenant inconnu : {f.container_type}"))
        if (f.origin, f.destination) not in data.duration_matrix:
            diagnostics.append(Diagnostic("matrice Durée", None, None, "CRITIQUE", "TRAJET_DUREE_ABSENT", f"Trajet absent dans matrice Durée : {f.origin} -> {f.destination}"))
        if (f.origin, f.destination) not in data.distance_matrix:
            diagnostics.append(Diagnostic("matrice Dist", None, None, "CRITIQUE", "TRAJET_DISTANCE_ABSENT", f"Trajet absent dans matrice Dist : {f.origin} -> {f.destination}"))
        if f.ready_time > f.due_time:
            diagnostics.append(Diagnostic("M flux", f.row_excel, None, "CRITIQUE", "FENETRE_INVERSEE", f"Fenêtre horaire inversée : {f.ready_time} > {f.due_time}"))
    return diagnostics


def split_oversized_flows(flows: list[Flow], max_capacity_func) -> list[Flow]:
    """Éclate les flux dont la quantité dépasse la meilleure capacité compatible."""
    output: list[Flow] = []
    for flow in flows:
        cap = max_capacity_func(flow)
        if cap <= 0:
            output.append(flow)
            continue
        n_parts = math.ceil(flow.quantity / cap)
        if n_parts <= 1:
            output.append(flow)
            continue
        remaining = flow.quantity
        for i in range(1, n_parts + 1):
            qty = min(cap, remaining)
            remaining -= qty
            output.append(flow.model_copy(update={"quantity": qty, "part_idx": i, "part_count": n_parts, "original_quantity": flow.quantity}))
    return output


def group_by_mutualized_name(flows: list[Flow]) -> list[list[Flow]]:
    """Regroupe les flux portant le même nom de tournée mutualisée."""
    groups: dict[str, list[Flow]] = defaultdict(list)
    singletons: list[list[Flow]] = []
    for flow in flows:
        if flow.mutualized_name:
            groups[flow.mutualized_name].append(flow)
        else:
            singletons.append([flow])
    return list(groups.values()) + singletons
