from models import Flow, Site, VehicleType
from compatibility import vehicle_compatible_with_flow, flows_sanitary_compatible


def test_without_dock_nc_blocks_vehicle():
    site = Site(name="A", has_dock=False, vehicle_compat={"V": True})
    vehicle = VehicleType(type="V", initial_site="A", length_m=3, width_m=2, max_weight_t=2, container_compat={"C": True}, manual_no_dock_min_per_container=None)
    flow = Flow(row_excel=2, id_flux=2, origin="A", destination="A", function="X", container_type="C", quantity=1, full_empty="Plein", clean_dirty="Propre", mixed_allowed=True, ready_time=360, due_time=900)
    ok, reason = vehicle_compatible_with_flow(vehicle, flow, {"A": site})
    assert not ok
    assert "sans quai" in reason


def test_clean_dirty_exclusion():
    f1 = Flow(row_excel=2, id_flux=2, origin="A", destination="B", function="X", container_type="C", quantity=1, full_empty="Plein", clean_dirty="Propre", mixed_allowed=True, mixed_exclusion="Sale", ready_time=360, due_time=900)
    f2 = Flow(row_excel=3, id_flux=3, origin="A", destination="B", function="X", container_type="C", quantity=1, full_empty="Plein", clean_dirty="Sale", mixed_allowed=True, mixed_exclusion="Propre", ready_time=360, due_time=900)
    ok, _ = flows_sanitary_compatible([f1, f2])
    assert not ok
