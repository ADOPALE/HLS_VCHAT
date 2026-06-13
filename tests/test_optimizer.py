from models import Flow, RoutePDTW, VehicleType, VisiteSite
from optimizer import Optimizer


def test_apply_insertion_adjusts_indices_without_data():
    # Test l'invariant d'index de l'insertion sans instancier de données complètes.
    opt = object.__new__(Optimizer)
    f = Flow(row_excel=2, id_flux=2, origin="A", destination="B", function="X", container_type="C", quantity=1, full_empty="Plein", clean_dirty="Propre", mixed_allowed=True, ready_time=360, due_time=900)
    visites = []
    new = Optimizer._apply_insertion(opt, visites, f, "new", 0, "new", 0)
    assert [v.site for v in new] == ["A", "B"]
    assert new[0].flux_charges[0].object_key == f.object_key
    assert new[1].flux_decharges[0].object_key == f.object_key
