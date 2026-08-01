# -*- coding: utf-8 -*-
"""The Wulf ViewModels' HAND-NUMBERED slot bookkeeping, checked without the engine.

Every model here declares its slot COUNT in `__init__(properties=N)` and then registers exactly N
properties in `_initialize`, with the setters addressing them by literal index. Nothing enforces
that: `_setNumber(i, v)` writes the i-th REGISTERED property, so appending a property without
raising `properties` allocates too few slots, and inserting one silently re-points every setter
after it at the wrong field. Both fail only in the live client -- the JS reads by NAME, so the
symptom is a widget showing another field's value (or a default forever), never an exception here.

The other test files exercise the models through a recording fake VM, which by construction cannot
see either mistake: the fake accepts any `set*` the real class declares and ignores `properties`
entirely. So this file reads the SOURCE instead. Engine-free -- Wulf is stubbed, nothing is
instantiated.
"""
import inspect
import re
import sys
import types


class _Permissive(object):
    def __init__(self, *a, **k):
        pass


for _name in ("frameworks", "frameworks.wulf"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
for _attr in ("ViewModel", "Array"):
    if not hasattr(sys.modules["frameworks.wulf"], _attr):
        setattr(sys.modules["frameworks.wulf"], _attr, _Permissive)

from moe_calculator.bridge import view_models              # noqa: E402


def _models():
    """Every ViewModel class view_models DEFINES (not the ones it imports), by name.

    Derived rather than hand-listed on purpose: a model added without a slot-count pin is exactly
    the drift this file exists to catch, and a hand-listed tuple would silently skip it."""
    out = {name: obj for name, obj in vars(view_models).items()
           if inspect.isclass(obj) and obj.__module__ == view_models.__name__}
    assert out, "view_models defines no ViewModel classes -- did the module move?"
    return out


def test_every_view_model_registers_exactly_its_declared_property_count():
    # THE append trap: `properties=N` is the slot allocation Wulf makes, and `_initialize` must
    # register exactly N. Appending `transEvents` / `transManual` to ProgressVM (9 -> 11) and
    # EfficiencyVM (12 -> 14) is the shape of change that gets this wrong, and it is invisible to a
    # recording fake VM (which ignores `properties` altogether).
    for name, cls in sorted(_models().items()):
        declared = inspect.signature(cls.__init__).parameters["properties"].default
        registered = len(re.findall(r"self\._add\w+Property\(", inspect.getsource(cls._initialize)))
        assert registered == declared, (
            "%s declares properties=%r but registers %d -- Wulf allocates the declared count, so "
            "the extra slot(s) are never addressable" % (name, declared, registered))


def test_no_accessor_addresses_a_slot_outside_the_declared_range():
    # THE renumbering trap's blast radius: every `_setBool/_setNumber/_setReal/_getArray` index must
    # land inside [0, properties). An out-of-range literal is a live-client write past the allocated
    # slots; a gap is legal (MoEVM's slot 9 is an Array read back through _getArray, not a setter),
    # so the ceiling is what is pinned, not contiguity.
    for name, cls in sorted(_models().items()):
        declared = inspect.signature(cls.__init__).parameters["properties"].default
        used = [int(i) for i in re.findall(r"self\._(?:set\w+|getArray)\((\d+),?",
                                           inspect.getsource(cls))]
        assert used, "%s has no indexed accessors at all" % name
        assert max(used) < declared, (
            "%s addresses slot %d but only declares properties=%r" % (name, max(used), declared))
        assert min(used) == 0, "%s never addresses slot 0" % name


def test_every_setter_addresses_the_slot_its_own_property_was_registered_at():
    # THE renumbering trap itself, which the two checks above only bound: they pin the COUNT and the
    # CEILING, so a setter pointed at a legal-but-wrong slot is green in both -- and green through
    # the recording fake VM too, which records by METHOD NAME and never sees an index. Appending
    # setShowEvents to ProgressVM at slot 10 instead of 11 (i.e. onto transManual's slot) passed the
    # entire suite; mutation-probed.
    #
    # Every model here names its setter after its property (`setShowEvents` <-> "showEvents"), all
    # 60 of them, so that convention IS the pin: read the registration ORDER out of _initialize and
    # require each setter's index to land on its own name. A slot with no setter is fine (MoEVM's
    # Array is read back through _getArray), which is why this walks setters, not slots.
    for name, cls in sorted(_models().items()):
        props = re.findall(r"self\._add\w+Property\(\s*[\"'](\w+)[\"']",
                           inspect.getsource(cls._initialize))
        setters = re.findall(r"def set(\w+)\(self[^)]*\):\s*\n\s*self\._set\w+\((\d+)",
                             inspect.getsource(cls))
        assert setters, "%s has no index-addressing setters at all" % name
        for setter, index in setters:
            expected = setter[0].lower() + setter[1:]
            assert props[int(index)] == expected, (
                "%s.set%s writes slot %s, which is registered as %r, not %r -- the setter is "
                "pointed at another field" % (name, setter, index, props[int(index)], expected))
