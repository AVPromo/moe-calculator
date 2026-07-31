# -*- coding: utf-8 -*-
"""The centre-screen DAMAGE EFFICIENCY bar as its own OpenWG-registered Gameface window -- the
radio ALTERNATIVE to the Moving Average bar (bridge/progress_view.py).

A thin instantiation of bridge/bar_window.BarHost, identical in shape to its sibling: read that
module for the hosting model and for why each bar keeps its OWN singleton, ModDynAccessor and
res_map entry. battle_bridge opens exactly ONE of the two, which is why both stylesheets can own
#moe-bar-root and the .mp-* namespace without colliding. Placement matches the sibling's shape
(centred horizontally, proportionally down the screen) but off its OWN anchor constants.

PC-only (needs the live client); not imported under pytest without stubs. Python 2.7 runtime.
"""
from moe_calculator.bridge.bar_window import BarHost
from moe_calculator.bridge.view_models import EfficiencyVM
from moe_calculator.domain.constants import (
    EFFICIENCY_ANCHOR_X_OFFSET, EFFICIENCY_ANCHOR_Y_FRAC, EFFICIENCY_ANCHOR_Y_OFFSET,
    EFFICIENCY_ANCHOR_Y_OFFSET_LARGE)

# itemID registered in mods/configs/res_map/MoEEfficiencyView.json -- keep in lockstep. It MUST
# differ from MoEBattleView's AND MoEProgressView's (the positional resId collision -- see
# bar_window).
RES_MAP_ITEM_ID = "MoEEfficiencyView"

_host = BarHost(RES_MAP_ITEM_ID, EfficiencyVM,
                EFFICIENCY_ANCHOR_Y_FRAC, EFFICIENCY_ANCHOR_X_OFFSET, EFFICIENCY_ANCHOR_Y_OFFSET,
                EFFICIENCY_ANCHOR_Y_OFFSET_LARGE, "[moe-eff]")

open_window = _host.open_window
close_window = _host.close_window
active_view = _host.active_view
apply_position = _host.apply_position
