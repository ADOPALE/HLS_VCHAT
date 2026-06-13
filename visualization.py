"""Visualisations Plotly pour l'interface Streamlit."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from time_windows import minutes_to_hhmm
from models import StepOperation


def gantt_by_driver(steps: list[StepOperation]):
    """Construit un diagramme de Gantt par poste chauffeur."""
    if not steps:
        return None
    rows = []
    base = pd.Timestamp("2026-01-01")
    for s in steps:
        rows.append({
            "Poste": s.post_id or s.route_id,
            "Opération": s.operation,
            "Début": base + pd.Timedelta(minutes=s.start_min),
            "Fin": base + pd.Timedelta(minutes=s.end_min),
            "Site": s.site or (f"{s.site_from} → {s.site_to}" if s.site_from else ""),
            "Flux": ", ".join(s.flux_keys),
        })
    df = pd.DataFrame(rows)
    fig = px.timeline(df, x_start="Début", x_end="Fin", y="Poste", color="Opération", hover_data=["Site", "Flux"])
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(xaxis_title="Horaire", yaxis_title="Poste chauffeur", legend_title="Opération")
    return fig
