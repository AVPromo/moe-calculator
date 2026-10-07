# -*- coding: utf-8 -*-
"""The four per-bar settings toggles must be named in the player docs exactly as the panel shows them."""
import io
import os

import pytest
from moe_calculator.adapter import settings_i18n as S

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_KEYS = ("progressShowPercent", "progressShowDelta", "efficiencyShowPercent", "efficiencyShowDelta")


def _doc(name):
    with io.open(os.path.join(_ROOT, name), encoding="utf-8") as handle:
        return handle.read()


def _missing(text, lang, keys=_KEYS):
    return [S._PANEL[lang][k]["label"] for k in keys if S._PANEL[lang][k]["label"] not in text]


@pytest.mark.parametrize("doc,lang", [("README.md", "en"), ("INSTALL.md", "en"), ("README.md", "uk")])
def test_per_bar_toggle_labels_are_documented(doc, lang):
    assert _missing(_doc(doc), lang) == []


def test_label_check_bites_on_a_mutated_doc():
    label = S._PANEL["en"][_KEYS[0]]["label"]
    mutated = _doc("README.md").replace(label, "")
    assert _missing(mutated, "en") == [label]
