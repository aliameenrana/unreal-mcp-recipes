#!/usr/bin/env python3
"""Builds and PIE-verifies the modal menus. Editor must be open with the MCP server on :8000.

  python3 recipes/ui/build/menus.py [pause|main|gameover ...] [--fresh] [--verify-only]
Screenshots go to $UI_OUT (default /tmp).
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import *

F = "/Game/UI"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
OUT = os.environ.get("UI_OUT", "/tmp")
QUIT = '\n  (Game|QuitGame :SpecificPlayer (Game|GetPlayerController 0))'
cls = lambda n: f"{F}/{n}.{n}_C"


def key_trigger(key, body):
    return f"""
(event AddEvent|EventTick (DeltaSeconds)
  (if (Game|Player|WasInputKeyJustPressed :self (Game|GetPlayerController 0) :Key "{key}"){body}))"""


MENUS = {
    "pause": {
        "spec": {"name": "WBP_Pause", "title": "Paused", "width": 420, "dim_alpha": 0.7,
                 "dismiss_key": "P", "dismiss": "DoResume",
                 "buttons": [{"id": "Resume", "label": "Resume", "style": "raised",
                              "body": CLOSE_TO_GAME + '\n  (Development|PrintString "UI_WBP_Pause_CLOSED")'},
                             {"id": "Quit", "label": "Quit to Desktop", "style": "danger", "body": QUIT}]},
        "boot": "BP_UIBoot",
        "boot_code": lambda: '(event AddEvent|EventBeginPlay (Development|PrintString "UI_BOOT_READY"))'
                             + key_trigger("P", open_menu_dsl(cls("WBP_Pause"), "UI_PAUSE_OPENED", True)),
        "open_key": "P", "opened": "UI_PAUSE_OPENED", "close_key": "P", "closed": "UI_WBP_Pause_CLOSED",
    },
    "main": {
        "spec": {"name": "WBP_MainMenu", "title": "Main Menu", "subtitle": "Press Enter to play",
                 "width": 480, "dim_alpha": 0.85, "accept_key": "Enter",
                 "buttons": [{"id": "Play", "label": "Play", "style": "raised",
                              "body": CLOSE_TO_GAME + '\n  (Development|PrintString "UI_WBP_MainMenu_PLAY")'},
                             {"id": "Quit", "label": "Quit", "style": "danger", "body": QUIT}]},
        "boot": "BP_UIBoot_Main",
        "boot_code": lambda: "(event AddEvent|EventBeginPlay"
                             + open_menu_dsl(cls("WBP_MainMenu"), "UI_MAIN_OPENED", True) + ")",
        "open_key": None, "opened": "UI_MAIN_OPENED", "close_key": "Enter", "closed": "UI_WBP_MainMenu_PLAY",
    },
    "gameover": {
        "spec": {"name": "WBP_GameOver", "title": "Game Over", "subtitle": "You were defeated",
                 "width": 480, "dim_alpha": 0.75, "accept_key": "Enter",
                 "buttons": [{"id": "Retry", "label": "Retry", "style": "raised",
                              "body": '\n  (Development|PrintString "UI_WBP_GameOver_RETRY")'
                                      '\n  (bind lvl (Game|GetCurrentLevelName :bRemovePrefixString true))'
                                      '\n  (Game|OpenLevel(byName) :LevelName (Utilities|String|StringToName lvl))'},
                             {"id": "Quit", "label": "Quit", "style": "danger", "body": QUIT}]},
        "boot": "BP_UIBoot_GameOver",
        "boot_code": lambda: '(event AddEvent|EventBeginPlay (Development|PrintString "UI_GAMEOVER_BOOT"))'
                             + key_trigger("G", open_menu_dsl(cls("WBP_GameOver"), "UI_GAMEOVER_OPENED", True)),
        "open_key": "G", "opened": "UI_GAMEOVER_OPENED", "close_key": "Enter", "closed": "UI_WBP_GameOver_RETRY",
        "after": lambda p: p.markers("UI_GAMEOVER_BOOT").count("UI_GAMEOVER_BOOT") >= 2 or "level did not reload",
    },
}


def build(key):
    m = MENUS[key]
    path = f"{F}/{m['spec']['name']}.{m['spec']['name']}"
    if "--fresh" in sys.argv and must("Asset", "exists", {"path": path}):
        must("Asset", "delete", {"path": path})
    build_menu(Theme(), F, m["spec"])
    boot = boot_actor(F, m["boot"], m["boot_code"](), LEVEL)
    save([path.split(".")[0], boot.split(".")[0]])


def verify(key):
    m = MENUS[key]
    boot = f"{F}/{m['boot']}.{m['boot']}"
    last_label = m["spec"]["buttons"][-1]["label"]
    for other in MENUS.values():
        if other is not m:
            unplace(LEVEL, f"{F}/{other['boot']}.{other['boot']}")
    place(LEVEL, boot, m["boot"])
    try:
        with PIE() as p:
            time.sleep(2)
            if m["open_key"]:
                p.key(m["open_key"])
            time.sleep(1)
            assert m["opened"] in p.markers(m["opened"]), f"{key}: menu did not open"
            assert p.button_ref(last_label), f"{key}: menu not on screen"
            p.capture(f"{OUT}/{m['spec']['name']}.png")
            p.key(m["close_key"], focus_game=False)
            time.sleep(1)
            assert m["closed"] in p.markers(m["closed"]), f"{key}: {m['close_key']} did not run its action"
            if key != "gameover":
                assert p.button_ref(last_label) is None, f"{key}: menu still on screen"
            if "after" in m:
                r = m["after"](p)
                assert r is True, f"{key}: {r}"
    finally:
        unplace(LEVEL, boot)
        save([LEVEL])
    print(f"{key.upper()} PASS")


if __name__ == "__main__":
    mcp.init()
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or list(MENUS)
    for k in keys:
        if "--verify-only" not in sys.argv:
            build(k)
        verify(k)
