"""Interface Streamlit OptiFLUX."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from config import WEEKDAYS
from data_loader import load_workbook_data
from engine import simulate_day
from exceptions import ImportBlockingError, InfeasibleProblemError, OptiFluxError
from outputs import export_results
from validators import validate_import_data
from visualization import gantt_by_driver

st.set_page_config(page_title="OptiFLUX", page_icon="🚚", layout="wide")


def diagnostics_to_df(diags):
    return pd.DataFrame([d.__dict__ for d in diags]) if diags else pd.DataFrame()


def init_state():
    for key, value in {"data": None, "import_errors": [], "import_warnings": [], "results": [], "precheck_ok": False}.items():
        st.session_state.setdefault(key, value)


def main():
    init_state()
    st.title("OptiFLUX — Optimisation logistique hospitalière multi-flux")
    st.caption("Import Excel, contrôles métier, optimisation VRPPDTW, planning chauffeurs/quais et exports détaillés.")

    tab_import, tab_params, tab_sim, tab_results, tab_export = st.tabs(["1. Import & Contrôles", "2. Paramètres", "3. Simulation", "4. Résultats", "5. Export"])

    with tab_import:
        st.subheader("Importer le fichier de paramétrage")
        file = st.file_uploader("Fichier Excel OptiFLUX", type=["xlsx"])
        if file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name
            try:
                data = load_workbook_data(tmp_path)
                warnings = validate_import_data(data)
                st.session_state.data = data
                st.session_state.import_errors = []
                st.session_state.import_warnings = warnings
                st.success("Fichier importé avec succès.")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Sites", len(data.sites))
                c2.metric("Véhicules", len(data.vehicles))
                c3.metric("Contenants", len(data.containers))
                c4.metric("Flux bruts", len(data.raw["M flux"]))
            except ImportBlockingError as exc:
                st.session_state.import_errors = exc.diagnostics
                st.session_state.data = None
                st.error("Import bloqué : corrige le fichier puis recharge-le.")
            except Exception as exc:
                st.session_state.data = None
                st.error(f"Erreur inattendue à l'import : {exc}")

        if st.session_state.import_errors:
            st.markdown("### Erreurs bloquantes")
            st.dataframe(diagnostics_to_df(st.session_state.import_errors), use_container_width=True)
        if st.session_state.import_warnings:
            st.markdown("### Alertes non bloquantes")
            st.dataframe(diagnostics_to_df(st.session_state.import_warnings), use_container_width=True)

    data = st.session_state.data
    if data is None:
        with tab_params:
            st.info("Importe d'abord un fichier valide.")
        with tab_sim:
            st.info("Importe d'abord un fichier valide.")
        return

    with tab_params:
        st.subheader("Paramètres de simulation")
        st.markdown("Les valeurs ci-dessous sont issues du fichier et peuvent être ajustées avant simulation.")
        c1, c2, c3, c4 = st.columns(4)
        data.rh.vacation_duration = int(c1.number_input("Durée de vacation (min)", min_value=60, max_value=720, value=int(data.rh.vacation_duration), step=5))
        data.rh.pause_duration = int(c2.number_input("Pause (min)", min_value=0, max_value=180, value=int(data.rh.pause_duration), step=5))
        data.rh.start_min = int(c3.number_input("Heure début mini (min depuis minuit)", min_value=0, max_value=1439, value=int(data.rh.start_min), step=5))
        data.rh.end_max = int(c4.number_input("Heure fin max (min depuis minuit)", min_value=0, max_value=1439, value=int(data.rh.end_max), step=5))
        traffic = st.slider("Facteur circulation (%)", min_value=0, max_value=100, value=0, step=5)
        st.session_state.traffic = traffic

        st.markdown("### Flotte")
        fleet_rows = []
        for vt, vehicle in data.vehicles.items():
            c1, c2 = st.columns([1, 1])
            vehicle.enabled = c1.checkbox(f"Activer {vt}", value=vehicle.enabled, key=f"veh_enabled_{vt}")
            max_val = c2.number_input(f"Nb max {vt} (0 = illimité)", min_value=0, value=0, step=1, key=f"veh_max_{vt}")
            vehicle.max_instances = None if max_val == 0 else int(max_val)
            fleet_rows.append({"Type": vt, "Stationnement initial": vehicle.initial_site, "Surface utile": round(vehicle.floor_area_m2, 2), "Sans quai possible": vehicle.manual_no_dock_min_per_container is not None})
        st.dataframe(pd.DataFrame(fleet_rows), use_container_width=True)

        st.markdown("### Capacité des quais")
        site_names = list(data.sites.keys())
        cols = st.columns(3)
        for i, site_name in enumerate(site_names):
            site = data.sites[site_name]
            site.dock_capacity = int(cols[i % 3].number_input(site_name, min_value=1, max_value=20, value=int(site.dock_capacity), step=1, key=f"dock_{site_name}"))

    with tab_sim:
        st.subheader("Lancer une simulation")
        selected_days = st.multiselect("Jours à simuler", WEEKDAYS, default=["Lundi"])
        functions = sorted([str(x) for x in data.raw["M flux"][data.column_maps["M flux"]["flow_function"]].dropna().unique()])
        selected_functions = st.multiselect("Fonctions support à inclure", functions, default=functions)
        if st.button("Lancer la simulation", type="primary", disabled=not bool(selected_days)):
            results = []
            progress = st.progress(0.0)
            status = st.empty()
            try:
                for i, day in enumerate(selected_days):
                    def cb(pct, msg, i=i, day=day):
                        global_pct = (i + pct) / len(selected_days)
                        progress.progress(min(1.0, global_pct))
                        status.write(f"{day} — {msg}")
                    result = simulate_day(data, day, selected_functions, traffic_factor_pct=st.session_state.get("traffic", 0), progress_callback=cb)
                    results.append(result)
                st.session_state.results = results
                progress.progress(1.0)
                status.success("Simulation terminée.")
            except InfeasibleProblemError as exc:
                st.error("Simulation bloquée : certains flux sont infaisables avec les paramètres actuels.")
                st.dataframe(diagnostics_to_df(exc.diagnostics), use_container_width=True)
            except OptiFluxError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.exception(exc)

    with tab_results:
        st.subheader("Résultats")
        results = st.session_state.results
        if not results:
            st.info("Aucun résultat pour le moment.")
        else:
            day_names = [r.day for r in results]
            selected_day = st.selectbox("Jour", day_names)
            result = next(r for r in results if r.day == selected_day)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Véhicules physiques", result.indicators["Nb véhicules (= véhicules physiques utilisés)"])
            c2.metric("Postes", result.indicators["Nb postes chauffeurs"])
            c3.metric("Km", result.indicators["Km totaux"])
            c4.metric("Taux service", f"{result.indicators['Taux de service (%)']}%")
            c5.metric("Flux non servis", len(result.unserved_flows))
            fig = gantt_by_driver(result.steps)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("### Timeline détaillée")
            st.dataframe(pd.DataFrame([s.model_dump() for s in result.steps]), use_container_width=True)
            st.markdown("### Planning des quais")
            st.dataframe(pd.DataFrame(result.dock_planning), use_container_width=True)
            st.markdown("### Contrôles")
            st.dataframe(pd.DataFrame(result.controls), use_container_width=True)

    with tab_export:
        st.subheader("Export Excel")
        if not st.session_state.results:
            st.info("Lance une simulation avant d'exporter.")
        elif st.button("Générer l'export Excel"):
            out = Path(tempfile.gettempdir()) / "OptiFLUX_resultats.xlsx"
            export_results(st.session_state.results, out)
            st.success("Export généré.")
            st.download_button("Télécharger l'export", data=out.read_bytes(), file_name="OptiFLUX_resultats.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    main()
