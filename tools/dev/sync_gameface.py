# -*- coding: utf-8 -*-
"""Hot-reload helper: copy ONLY the Gameface front-end assets (MoECalculator.js
/ .css) into the client's res_mods overlay, so visual changes can be applied
WITHOUT relaunching the client.

WoT's `coui://gui/...` resolves through a merged virtual filesystem where
`res_mods/<version>/` outranks the packaged `.wotmod`. The hangar sub-view
document re-fetches our assets every time it's (re)built, so after a sync you
just switch to another screen and back to the garage and the new CSS/JS loads.

This is for VISUAL (JS/CSS) iteration only. Python changes (the mount logic in
the .wotmod) still require build + deploy + relaunch via deploy_wotmod.py.

Usage (any Python 3, client may stay running):
    python tools/dev/sync_gameface.py "D:/Games/World_of_Tanks_EU" 2.3.0.1

Note: this leaves a loose res_mods overlay in place. It only shadows the .wotmod's
COPY of the SAME assets (intended) -- it does NOT shadow the Python entry point,
so the mod keeps loading normally. Remove it before shipping / final verify if
you want to confirm the packaged assets render identically.
"""
import os
import shutil
import sys

REL = os.path.join("gui", "gameface", "mods", "14th_ua", "MoECalculator")
# Every file in the MoECalculator asset dir is synced (mirrors what the packaged
# build ships) -- globbing rather than a hand-kept name list, so a NEW asset can
# never be silently forgotten here (a missing name would let the packaged .wotmod
# copy shadow it and serve a stale file, exactly the trap this loop exists to beat).
# Includes MoEBattle.ttf, a bare sibling of the CSS (Coherent @font-face resolves
# only bare-sibling src urls). NOTE the battle WINDOW has no in-session hot-reload
# (its resources pin at launch) -- MoEBattle.* changes still need a client relaunch.


def main(argv):
    if len(argv) != 3:
        print("usage: sync_gameface.py <wot_install_dir> <version>")
        return 2
    install, version = argv[1], argv[2]
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "..", "..", "src", "res", REL)
    dst = os.path.join(install, "res_mods", version, REL)
    if not os.path.isdir(src):
        print("source assets not found: %s" % os.path.abspath(src))
        return 1
    if not os.path.isdir(os.path.join(install, "res_mods", version)):
        print("res_mods/%s not found under %s" % (version, install))
        return 1
    if not os.path.isdir(dst):
        os.makedirs(dst)
    count = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        rel_dir = os.path.relpath(root, src)
        dst_dir = dst if rel_dir == "." else os.path.join(dst, rel_dir)
        if not os.path.isdir(dst_dir):
            os.makedirs(dst_dir)
        for name in sorted(files):
            if name.endswith((".pyc", "~", ".bak", ".swp")):
                continue
            shutil.copy2(os.path.join(root, name), os.path.join(dst_dir, name))
            count += 1
            print("synced: %s" % os.path.join(dst_dir, name))
    missing = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel_dir = os.path.relpath(root, src)
        for name in files:
            if name.endswith((".pyc", "~", ".bak", ".swp")):
                continue
            rel_file = name if rel_dir == "." else os.path.join(rel_dir, name)
            if not os.path.isfile(os.path.join(dst, rel_file)):
                missing.append(rel_file)
    if missing:
        print("ERROR: overlay missing %d file(s) after sync:" % len(missing))
        for rel_file in missing:
            print("  missing: %s" % rel_file)
        return 1
    print("Done (%d files). In-game: switch screen (e.g. to Tech Tree) and back to reload." % count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
