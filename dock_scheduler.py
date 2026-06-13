"""Planning des quais et contrôle de capacité simultanée."""

from __future__ import annotations

from collections import defaultdict

from data_loader import OptiFluxData
from models import StepOperation


def build_dock_planning(data: OptiFluxData, day: str, steps: list[StepOperation]) -> tuple[list[dict], list[dict]]:
    """Construit le planning des quais et signale les conflits de capacité."""
    rows: list[dict] = []
    controls: list[dict] = []
    for step in steps:
        if step.operation != "Quai + manutention" or not step.site:
            continue
        site = data.sites[step.site]
        rows.append({
            "Jour": day,
            "Site": step.site,
            "Capacité quai": site.dock_capacity,
            "Heure arrivée": step.start_min,
            "Heure début mise à quai": step.start_min,
            "Heure fin mise à quai": step.end_min,
            "Heure départ": step.end_min,
            "Véhicule": step.vehicle_instance or step.vehicle_type,
            "Opération": step.operation,
            "Flux concernés": ", ".join(step.flux_keys),
        })
    by_site: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_site[row["Site"]].append(row)
    for site_name, entries in by_site.items():
        capacity = data.sites[site_name].dock_capacity
        points = []
        for row in entries:
            points.append((row["Heure début mise à quai"], 1, row))
            points.append((row["Heure fin mise à quai"], -1, row))
        points.sort(key=lambda x: (x[0], x[1]))
        current = 0
        max_seen = 0
        for _, delta, _ in points:
            current += delta
            max_seen = max(max_seen, current)
        if max_seen > capacity:
            controls.append({
                "Jour": day,
                "Type de contrôle": "CONFLIT_QUAI",
                "Statut": "ALERTE",
                "Détail": f"{site_name}: {max_seen} véhicules simultanés pour capacité {capacity}",
                "Flux ou véhicule concerné": site_name,
                "Gravité": "ALERTE",
                "Action recommandée": "Augmenter la capacité quai ou décaler des tournées ; l'algorithme conserve les fenêtres horaires prioritaires.",
            })
    return rows, controls
