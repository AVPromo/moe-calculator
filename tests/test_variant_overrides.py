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


# --- should_auto_toggle: the automatic per-vehicle mode-toggle predicate, pure --------------

def test_should_auto_toggle_false_at_the_disable_sentinel():
    # threshold == 100 is the DISABLE sentinel -- never fires even at a perfect pct.
    assert vo.should_auto_toggle(100, 100.0, 0, 0) is False


def test_should_auto_toggle_false_above_the_sentinel():
    # A threshold above 100 (corrupt/clamped-away-from) is equally disabled.
    assert vo.should_auto_toggle(150, 100.0, 0, 0) is False


def test_should_auto_toggle_false_when_pct_is_none():
    # No trustworthy baseline this mount -- never fire off an untrustworthy read.
    assert vo.should_auto_toggle(50, None, 0, 0) is False


def test_should_auto_toggle_false_when_pct_below_threshold():
    assert vo.should_auto_toggle(50, 49.9, 0, 0) is False


def test_should_auto_toggle_true_when_pct_meets_threshold_and_not_overridden():
    assert vo.should_auto_toggle(50, 50.0, 0, 0) is True


def test_should_auto_toggle_false_when_already_overridden():
    # Idempotence guard: a repeat qualifying battle must NOT re-flip an already-overridden bar.
    assert vo.should_auto_toggle(50, 90.0, 1, 0) is False


def test_should_auto_toggle_true_at_the_boundary_pct_equals_threshold():
    # At-or-above is inclusive.
    assert vo.should_auto_toggle(65, 65.0, 0, 0) is True
