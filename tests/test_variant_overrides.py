import os
import pytest
from moe_calculator.adapter import variant_overrides as vo
from moe_calculator.adapter import moe_wgapi


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(moe_wgapi, "data_dir", lambda: str(tmp_path))
    return tmp_path


def test_effective_falls_back_to_default_when_absent(store):
    assert vo.effective(123, 0) == 0
    assert vo.effective(123, 1) == 1
    assert vo.effective(None, 1) == 1


def test_toggle_stores_when_differs_from_default(store):
    assert vo.toggle(123, 0) == 1
    assert vo.load() == {123: 1}
    assert vo.effective(123, 0) == 1


def test_toggle_prunes_when_equals_default(store):
    vo.save({123: 1})
    assert vo.toggle(123, 0) == 0
    assert vo.load() == {}
    assert vo.effective(123, 0) == 0


def test_corrupt_file_reads_as_empty(store):
    with open(os.path.join(str(store), vo.OVERRIDES_FILE), "wb") as fh:
        fh.write(b"{not json")
    assert vo.load() == {}


def test_load_coerces_str_keys_and_drops_bool_and_out_of_range(store):
    # save()'s own coercion would reject these before they ever hit disk, so write the RAW
    # blob straight through moe_wgapi to exercise load()'s drop branches.
    moe_wgapi.write_json(os.path.join(str(store), vo.OVERRIDES_FILE), {"1": True, "2": 9, "3": 0})
    assert vo.load() == {3: 0}
