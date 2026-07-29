# -*- coding: utf-8 -*-
"""The centre-screen transient MoE progress bar (the "Moving Average" variant) as its own
OpenWG-registered Gameface window.

A thin instantiation of bridge/bar_window.BarHost -- read that module for the whole hosting model
(why a registered window, why WindowLayer.WINDOW, why NOT WINDOW_FULLSCREEN, why the surface size is
a JS push, why each bar needs its OWN singleton and ModDynAccessor). The bar-specific facts are the
five arguments below and nothing else. The module-level functions stay module-level because
battle_bridge (and its tests) treat this module AS the window handle.

PC-only (needs the live client); not imported under pytest without stubs. Python 2.7 runtime.
"""
from moe_calculator.bridge.bar_window import BarHost
from moe_calculator.bridge.view_models import ProgressVM
from moe_calculator.domain.constants import (
    PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_OFFSET)

# itemID registered in mods/configs/res_map/MoEProgressView.json -- keep in lockstep. It MUST
# differ from every other entry's: OpenWG assigns the numeric resId positionally when it rebuilds
# res_map.json, so two entries sharing an itemID collide and one layout becomes unreachable.
RES_MAP_ITEM_ID = "MoEProgressView"

_host = BarHost(RES_MAP_ITEM_ID, ProgressVM,
                PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_OFFSET,
                "[moe-bar]")

open_window = _host.open_window
close_window = _host.close_window
active_view = _host.active_view
apply_position = _host.apply_position
