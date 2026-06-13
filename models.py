"""Modèles de données métier OptiFLUX.

Les modèles sont volontairement explicites pour faciliter le débogage par des
non-développeurs : chaque objet porte les données nécessaires à la traçabilité
des décisions d'optimisation.
"""

from __future__ import annotations

from typing import Callable, Literal
from pydantic import BaseModel, Field, ConfigDict


class RHParams(BaseModel):
    vacation_duration: int
    pause_duration: int
    start_min: int
    end_max: int

    @property
    def useful_one_shift_duration(self) -> int:
        from config import PICKUP_PREP_MIN, END_OF_SHIFT_MIN
        return self.vacation_duration - self.pause_duration - PICKUP_PREP_MIN - END_OF_SHIFT_MIN


class Site(BaseModel):
    name: str
    address: str | None = None
    has_dock: bool = True
    dock_capacity: int = 1
    vehicle_compat: dict[str, bool] = Field(default_factory=dict)


class VehicleType(BaseModel):
    type: str
    initial_site: str
    length_m: float
    width_m: float
    height_m: float | None = None
    max_weight_t: float
    consumption_l_km: float = 0.0
    fuel_cost_per_km: float = 0.0
    co2_kg_per_km: float = 0.0
    has_tail_lift: bool = False
    container_compat: dict[str, bool] = Field(default_factory=dict)
    dock_time_min: int = 0
    manual_no_dock_min_per_container: float | None = None
    manual_dock_min_per_container: float = 0.0
    enabled: bool = True
    max_instances: int | None = None

    @property
    def floor_area_m2(self) -> float:
        return max(0.0, self.length_m * self.width_m)


class ContainerType(BaseModel):
    name: str
    length_m: float
    width_m: float
    empty_weight_t: float
    full_weight_t: float


class Flow(BaseModel):
    row_excel: int
    id_flux: int
    origin: str
    destination: str
    function: str
    label: str | None = None
    container_type: str
    quantity: int
    full_empty: str
    clean_dirty: str
    mixed_allowed: bool
    mixed_exclusion: str | None = None
    mutualized_name: str | None = None
    ready_time: int
    due_time: int
    priority: bool = False
    original_quantity: int | None = None
    part_idx: int = 1
    part_count: int = 1

    @property
    def object_key(self) -> str:
        return f"F{self.id_flux}-P{self.part_idx}/{self.part_count}-R{self.row_excel}"

    @property
    def is_split(self) -> bool:
        return self.part_count > 1


class VisiteSite(BaseModel):
    site: str
    flux_charges: list[Flow] = Field(default_factory=list)
    flux_decharges: list[Flow] = Field(default_factory=list)

    def clone(self) -> "VisiteSite":
        return VisiteSite(site=self.site, flux_charges=list(self.flux_charges), flux_decharges=list(self.flux_decharges))

    def is_empty(self) -> bool:
        return not self.flux_charges and not self.flux_decharges


class RoutePDTW(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    route_id: str
    vehicle: VehicleType
    visites: list[VisiteSite] = Field(default_factory=list)
    scheduled_start: int | None = None
    scheduled_end: int | None = None
    distance_km: float = 0.0
    loaded_km: float = 0.0
    empty_km: float = 0.0
    duration_min: int = 0
    feasible: bool = True
    infeasibility_reason: str | None = None

    def clone(self) -> "RoutePDTW":
        return RoutePDTW(
            route_id=self.route_id,
            vehicle=self.vehicle,
            visites=[v.clone() for v in self.visites],
            scheduled_start=self.scheduled_start,
            scheduled_end=self.scheduled_end,
            distance_km=self.distance_km,
            loaded_km=self.loaded_km,
            empty_km=self.empty_km,
            duration_min=self.duration_min,
            feasible=self.feasible,
            infeasibility_reason=self.infeasibility_reason,
        )

    @property
    def flux(self) -> list[Flow]:
        seen: set[str] = set()
        out: list[Flow] = []
        for visite in self.visites:
            for f in visite.flux_charges + visite.flux_decharges:
                if f.object_key not in seen:
                    seen.add(f.object_key)
                    out.append(f)
        return out

    @property
    def has_dirty(self) -> bool:
        return any(str(f.clean_dirty).strip().casefold() == "sale" for f in self.flux)

    @property
    def has_clean(self) -> bool:
        return any(str(f.clean_dirty).strip().casefold() == "propre" for f in self.flux)


class StepOperation(BaseModel):
    day: str
    route_id: str
    post_id: str | None = None
    vehicle_instance: str | None = None
    vehicle_type: str
    order: int
    start_min: int
    end_min: int
    operation: str
    site: str | None = None
    site_from: str | None = None
    site_to: str | None = None
    flux_keys: list[str] = Field(default_factory=list)
    loaded_containers: dict[str, int] = Field(default_factory=dict)
    unloaded_containers: dict[str, int] = Field(default_factory=dict)
    fill_rate_surface_pct: float | None = None
    distance_km: float = 0.0
    duration_min: int = 0
    sanitary_state: str = "Propre"
    empty_leg: bool = False
    comment: str | None = None


class DriverPost(BaseModel):
    day: str
    post_id: str
    vehicle_instance: str
    vehicle_type: str
    route_id: str
    start_min: int
    end_min: int
    steps: list[StepOperation] = Field(default_factory=list)
    disinfections: int = 0
    conduite_min: int = 0
    manutention_min: int = 0
    quai_min: int = 0
    attente_min: int = 0
    inoccuped_min: int = 0


class DayResult(BaseModel):
    day: str
    routes: list[RoutePDTW]
    steps: list[StepOperation]
    posts: list[DriverPost]
    dock_planning: list[dict]
    transported_flows: list[dict]
    unserved_flows: list[dict]
    controls: list[dict]
    indicators: dict
