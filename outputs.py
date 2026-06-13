"""Génération des exports Excel OptiFLUX via xlsxwriter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from models import DayResult, StepOperation
from time_windows import minutes_to_hhmm


def _fmt_min(v: Any) -> Any:
    if isinstance(v, (int, float)):
        return minutes_to_hhmm(v)
    return v


def _steps_rows(steps: list[StepOperation]) -> list[dict]:
    rows = []
    for s in steps:
        rows.append({
            "Jour": s.day,
            "N° Tournée": s.route_id,
            "Véhicule": s.vehicle_instance,
            "Type de véhicule": s.vehicle_type,
            "Ordre": s.order,
            "Heure début": minutes_to_hhmm(s.start_min),
            "Heure fin": minutes_to_hhmm(s.end_min),
            "Site départ": s.site_from,
            "Site arrivée": s.site_to or s.site,
            "Type opération": s.operation,
            "Flux IDs": ", ".join(s.flux_keys),
            "Contenants chargés": str(s.loaded_containers or ""),
            "Contenants déchargés": str(s.unloaded_containers or ""),
            "Taux rempl. surf. (%)": s.fill_rate_surface_pct,
            "Distance (km)": round(s.distance_km, 2),
            "Durée (min)": s.duration_min,
            "État sanitaire": s.sanitary_state,
            "À vide ?": "OUI" if s.empty_leg else "NON",
        })
    return rows


def export_results(results: list[DayResult], output_path: str | Path) -> Path:
    """Crée l'export Excel complet de résultats."""
    output_path = Path(output_path)
    indicators = [r.indicators for r in results]
    fleet_rows = []
    driver_rows = []
    route_rows = []
    planning_driver_rows = []
    dock_rows = []
    transported_rows = []
    unserved_rows = []
    controls_rows = []

    for result in results:
        route_rows.extend(_steps_rows(result.steps))
        dock_rows.extend(result.dock_planning)
        transported_rows.extend(result.transported_flows)
        unserved_rows.extend(result.unserved_flows)
        controls_rows.extend(result.controls)
        by_vehicle: dict[str, dict] = {}
        for route in result.routes:
            row = by_vehicle.setdefault(route.vehicle.type, {"Jour": result.day, "Type de véhicule": route.vehicle.type, "Véhicules physiques utilisés": 0, "Nb tournées": 0, "Km totaux": 0.0, "Km à plein": 0.0, "Km à vide": 0.0, "Désinfections": 0, "Coût estimé (€)": 0.0, "Émissions CO₂ (kg)": 0.0})
            row["Nb tournées"] += 1
            row["Km totaux"] += route.distance_km
            row["Km à plein"] += route.loaded_km
            row["Km à vide"] += route.empty_km
            row["Coût estimé (€)"] += route.distance_km * route.vehicle.fuel_cost_per_km
            row["Émissions CO₂ (kg)"] += route.distance_km * route.vehicle.co2_kg_per_km
        instances_by_type: dict[str, set[str]] = {}
        for post in result.posts:
            instances_by_type.setdefault(post.vehicle_type, set()).add(post.vehicle_instance)
            duration = post.end_min - post.start_min
            occupation = min(100.0, (post.conduite_min + post.manutention_min + post.quai_min) / max(1, duration) * 100)
            inoccuped = min(100.0, post.inoccuped_min / max(1, duration) * 100)
            driver_rows.append({
                "Jour": post.day,
                "Poste": post.post_id,
                "Véhicule": post.vehicle_instance,
                "Heure début": minutes_to_hhmm(post.start_min),
                "Heure fin": minutes_to_hhmm(post.end_min),
                "Durée (min)": duration,
                "Prise de poste (min)": 15,
                "Fin de poste (min)": 10,
                "Pause (min)": result.indicators.get("pause_duration", 0),
                "Conduite (min)": post.conduite_min,
                "Manutention (min)": post.manutention_min,
                "Quai (min)": post.quai_min,
                "Désinfection (min)": post.disinfections * 15,
                "Attente (min)": post.attente_min,
                "Inoccupé (min)": post.inoccuped_min,
                "Taux occupation (%)": round(occupation, 1),
                "Taux inoccupé (%)": round(inoccuped, 1),
            })
            for s in post.steps:
                planning_driver_rows.append({
                    "Jour": s.day,
                    "Poste": post.post_id,
                    "Véhicule": post.vehicle_instance,
                    "Ordre": s.order,
                    "Heure début": minutes_to_hhmm(s.start_min),
                    "Heure fin": minutes_to_hhmm(s.end_min),
                    "Type opération": s.operation,
                    "Site": s.site or (f"{s.site_from} → {s.site_to}" if s.site_from else ""),
                    "Flux concernés": ", ".join(s.flux_keys),
                    "Commentaire": s.comment,
                })
        for vt, instances in instances_by_type.items():
            if vt in by_vehicle:
                by_vehicle[vt]["Véhicules physiques utilisés"] = len(instances)
        fleet_rows.extend(by_vehicle.values())

    sheets = {
        "Indicateurs": pd.DataFrame(indicators),
        "Synthèse flotte": pd.DataFrame(fleet_rows),
        "Synthèse chauffeurs": pd.DataFrame(driver_rows),
        "Tournées véhicules": pd.DataFrame(route_rows),
        "Planning chauffeurs": pd.DataFrame(planning_driver_rows),
        "Planning quais": pd.DataFrame(dock_rows),
        "Flux transportés": pd.DataFrame(transported_rows),
        "Flux non servis": pd.DataFrame(unserved_rows),
        "Contrôles contraintes": pd.DataFrame(controls_rows),
    }
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        for name, df in sheets.items():
            if df.empty:
                df = pd.DataFrame({"Information": []})
            df.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            workbook = writer.book
            header_fmt = workbook.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white", "border": 1})
            cell_fmt = workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"})
            for col_num, value in enumerate(df.columns.values):
                ws.write(0, col_num, value, header_fmt)
                max_len = max([len(str(value))] + [len(str(x)) for x in df[value].head(200).fillna("")])
                ws.set_column(col_num, col_num, min(max(max_len + 2, 12), 45), cell_fmt)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
    return output_path
