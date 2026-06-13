from models import ContainerType, Flow, VehicleType
from capacity import discrete_floor_capacity, max_containers_for_flow


def _flow(qty=1, full_empty="Plein"):
    return Flow(row_excel=2, id_flux=2, origin="A", destination="B", function="X", container_type="Roll", quantity=qty, full_empty=full_empty, clean_dirty="Propre", mixed_allowed=True, ready_time=360, due_time=900)


def test_capacity_rotation_and_weight():
    vehicle = VehicleType(type="V", initial_site="A", length_m=3.0, width_m=2.0, max_weight_t=2.0, container_compat={"Roll": True})
    container = ContainerType(name="Roll", length_m=1.2, width_m=0.8, empty_weight_t=0.1, full_weight_t=0.5)
    assert discrete_floor_capacity(vehicle, container) == 4
    assert max_containers_for_flow(vehicle, container, _flow()) == 4
