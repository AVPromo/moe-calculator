# -*- coding: utf-8 -*-
"""`_compat._scrub_paths` -- must never leak a player's username/install path into
python.log, whether or not the frame anchors on scripts/client/.

Stance under test: over-scrub is fine, a leak is not. Every assertion here checks the
scrubbed output does NOT contain the fake username/host token the input path carried.
"""
from moe_calculator import _compat


def test_scrub_windows_absolute_frame_keeps_scripts_client_tail():
    line = (
        'File "C:\\Users\\johnsmith\\AppData\\Local\\Wargaming.net\\WOT\\mods\\2.3.1.2\\'
        'com.14th_ua.moe_calculator_3.1.0.wotmod\\res\\scripts\\client\\moe_calculator\\'
        'domain\\builder.py", line 42, in build_model'
    )
    out = _compat._scrub_paths(line)
    assert "johnsmith" not in out
    assert 'File "moe_calculator\\domain\\builder.py"' in out
    assert "line 42, in build_model" in out


def test_scrub_forward_slash_windows_frame():
    line = (
        'File "C:/Users/johnsmith/AppData/Local/Wargaming.net/WOT/mods/2.3.1.2/'
        'com.14th_ua.moe_calculator_3.1.0.wotmod/res/scripts/client/moe_calculator/'
        'domain/builder.py", line 7, in <module>'
    )
    out = _compat._scrub_paths(line)
    assert "johnsmith" not in out
    assert 'File "moe_calculator/domain/builder.py"' in out


def test_scrub_unc_frame_falls_back_to_basename():
    line = 'File "\\\\BUILDHOST\\share\\project\\foo.py", line 5, in <module>'
    out = _compat._scrub_paths(line)
    assert "BUILDHOST" not in out
    assert 'File "foo.py"' in out


def test_scrub_posix_absolute_frame_falls_back_to_basename():
    line = 'File "/home/johnsmith/project/foo.py", line 7, in <module>'
    out = _compat._scrub_paths(line)
    assert "johnsmith" not in out
    assert 'File "foo.py"' in out


def test_scrub_frame_with_no_scripts_client_anchor_falls_back_to_basename():
    # e.g. a WG-shipped module under res/scripts/common/ -- no scripts/client segment.
    line = 'File "C:\\Users\\johnsmith\\WOT\\res\\scripts\\common\\items.py", line 3, in <module>'
    out = _compat._scrub_paths(line)
    assert "johnsmith" not in out
    assert 'File "items.py"' in out


def test_scrub_multi_frame_traceback_scrubs_every_frame():
    text = (
        "Traceback (most recent call last):\n"
        '  File "C:\\Users\\johnsmith\\WOT\\res\\scripts\\common\\items.py", line 3, in <module>\n'
        '    File "C:\\Users\\johnsmith\\WOT\\mods\\install\\scripts\\client\\moe_calculator\\'
        'domain\\builder.py", line 42, in build_model\n'
        "ValueError: boom"
    )
    out = _compat._scrub_paths(text)
    assert "johnsmith" not in out
    assert 'File "items.py"' in out
    assert 'File "moe_calculator\\domain\\builder.py"' in out


def test_scrub_frame_with_apostrophe_in_username_scrubs_whole_prefix():
    # A literal apostrophe in the username must not stop the fallback char class early --
    # only the basename should survive.
    line = (
        'File "C:\\Users\\O\'Brien\\WOT\\res\\scripts\\common\\items.py", line 3, in <module>'
    )
    out = _compat._scrub_paths(line)
    assert "O'Brien" not in out
    assert "Brien" not in out
    assert "Users" not in out
    assert 'File "items.py"' in out


def test_scrub_passthrough_line_with_no_path_is_unchanged():
    line = "ValueError: something went wrong"
    assert _compat._scrub_paths(line) == line
