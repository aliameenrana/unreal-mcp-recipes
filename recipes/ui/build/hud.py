#!/usr/bin/env python3
"""Builds and PIE-verifies the in-game HUD: health bar top-left, score top-right, prompt bottom-center.

  python3 recipes/ui/build/hud.py [--fresh] [--verify-only]
The HUD reads three public variables every tick: Health (0..1), Score (int), ShowPrompt (bool).
Gameplay code sets them on the widget reference it created.
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import *

F, NAME, BOOT = "/Game/UI", "WBP_HUD", "BP_UIBoot_HUD"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
OUT = os.environ.get("UI_OUT", "/tmp")
PATH = f"{F}/{NAME}.{NAME}"


def build(th):
    bp = WidgetBP(F, NAME)
    bp.create()
    bp.add("SafeZone", "Safe")
    bp.add("CanvasPanel", "Root", "Safe")
    bp.add("Border", "HealthCard", "Root")
    bp.add("VerticalBox", "HealthStack", "HealthCard")
    bp.add("TextBlock", "HealthLabel", "HealthStack")
    bp.add("SizeBox", "HealthSize", "HealthStack")
    bp.add("ProgressBar", "HealthBar", "HealthSize", variable=True)
    bp.add("Border", "ScoreCard", "Root")
    bp.add("VerticalBox", "ScoreStack", "ScoreCard")
    bp.add("TextBlock", "ScoreLabel", "ScoreStack")
    bp.add("TextBlock", "ScoreValue", "ScoreStack", variable=True)
    bp.add("Border", "PromptCard", "Root", variable=True)
    bp.add("TextBlock", "PromptText", "PromptCard")

    sp = th.t["spacing"]
    card = {"background": th.brush("surface"), "padding": {"left": sp["inner"], "top": sp["gap"],
                                                           "right": sp["inner"], "bottom": sp["gap"]}}
    small = {"fontObject": th.t["font"]["asset"], "typefaceFontName": "Bold", "size": th.t["sizes"]["small"]}

    bp.set("slot:HealthCard", canvas_at(0, 0, sp["outer"], sp["outer"]))
    bp.set("HealthCard", card)
    bp.set("HealthLabel", {"text": "HEALTH", "font": small, "colorAndOpacity": th.color("text_muted")})
    bp.set("slot:HealthLabel", {"padding": {"left": 0, "top": 0, "right": 0, "bottom": 6}})
    bp.set("HealthSize", {"bOverride_WidthOverride": True, "widthOverride": 320,
                          "bOverride_HeightOverride": True, "heightOverride": 18})
    bp.set("HealthBar", {"percent": 1.0, "fillColorAndOpacity": th.t["colors"]["accent"],
                         "widgetStyle": {"backgroundImage": th.brush("raised", radius=6),
                                         "fillImage": th.brush("text", radius=6)}})

    bp.set("slot:ScoreCard", canvas_at(1, 0, -sp["outer"], sp["outer"]))
    bp.set("ScoreCard", card)
    bp.set("ScoreLabel", {"text": "SCORE", "font": small, "colorAndOpacity": th.color("text_muted"),
                          "justification": "Right"})
    bp.set("ScoreValue", {"text": "0", "font": th.font("title"), "colorAndOpacity": th.color("text"),
                          "justification": "Right"})
    for s in ("ScoreLabel", "ScoreValue"):
        bp.set("slot:" + s, {"horizontalAlignment": "HAlign_Right"})

    bp.set("slot:PromptCard", canvas_at(0.5, 1, 0, -96))
    bp.set("PromptCard", card)
    bp.set("PromptText", {"text": "Press E to interact", "font": th.font("body"), "colorAndOpacity": th.color("text")})

    bp.var("Health", "real")
    bp.var("Score", "int")
    bp.var("ShowPrompt", "bool")
    bp.graph(f"""
(event UserInterface|EventTick (MyGeometry InDeltaTime)
  (Progress|SetPercent :self (Variables|{NAME}|GetHealthBar) :InPercent (Variables|Default|GetHealth))
  (Widget|SetText(Text) :self (Variables|{NAME}|GetScoreValue) :InText (Utilities|Text|ToText(Integer) (Variables|Default|GetScore)))
  (Widget|SetRenderOpacity :self (Variables|{NAME}|GetPromptCard) :InOpacity (select (Variables|Default|GetShowPrompt) 1.0 0.0)))
""")
    bp.compile()
    must("Object", "set_properties", {"instance": ref(f"{F}/{NAME}.Default__{NAME}_C"), "values": '{"Health": 1.0}'})
    return bp


if __name__ == "__main__":
    mcp.init()
    if "--fresh" in sys.argv:
        # The boot actor goes too: its Hud variable is typed to the old WBP_HUD class.
        boot = f"{F}/{BOOT}.{BOOT}"
        fresh_wipe(LEVEL, [boot], [boot, PATH])
    if "--verify-only" not in sys.argv:
        build(Theme())


BOOT_CODE = f"""
(event AddEvent|EventBeginPlay
  (bind pc (Game|GetPlayerController 0))
  (bind w (UserInterface|CreateWidget :Class "{F}/{NAME}.{NAME}_C" :OwningPlayer pc))
  (Variables|Default|SetHud w)
  (UserInterface|Viewport|AddtoViewport :self w :ZOrder 0)
  (Development|PrintString "UI_HUD_SHOWN"))
(event AddEvent|EventTick (DeltaSeconds)
  (if (Game|Player|WasInputKeyJustPressed :self (Game|GetPlayerController 0) :Key "H")
    (bind h (Variables|Default|GetHud))
    (Class|WBPHUD|SetHealth :self h :Health (- (Class|WBPHUD|GetHealth :self h) 0.25))
    (Class|WBPHUD|SetScore :self h :Score (+ (Class|WBPHUD|GetScore :self h) 10))
    (Class|WBPHUD|SetShowPrompt :self h :ShowPrompt true)
    (Development|PrintString "UI_HUD_UPDATED")))
"""


def build_boot():
    path = f"{F}/{BOOT}.{BOOT}"
    if not must("Asset", "exists", {"path": path}):
        must("BP", "create", {"folder_path": F, "asset_name": BOOT, "asset_type": ref("/Script/Engine.Actor")})
        must("BP", "add_object_variable", {"blueprint": ref(path), "name": "Hud",
             "object_class": ref(f"{F}/{NAME}.{NAME}_C"), "graph": None, "container_type": None})
    must("BP", "write_graph_dsl", {"graph": path + ":EventGraph", "code": BOOT_CODE})
    save([PATH.split(".")[0], path.split(".")[0]])
    return path


def texts(p):
    return [l.strip() for l in p.snapshot().splitlines() if l.strip().startswith("text ")]


def verify(boot):
    for other in ("BP_UIBoot", "BP_UIBoot_Main", "BP_UIBoot_GameOver"):
        unplace(LEVEL, f"{F}/{other}.{other}")
    place(LEVEL, boot, BOOT)
    try:
        with PIE() as p:
            time.sleep(3)
            assert "UI_HUD_SHOWN" in p.markers("UI_HUD_SHOWN"), "HUD not created"
            t = " ".join(texts(p))
            assert '"HEALTH"' in t and '"SCORE"' in t and '"0"' in t, f"HUD text missing: {t[:300]}"
            p.key("H")
            time.sleep(1)
            assert "UI_HUD_UPDATED" in p.markers("UI_HUD_UPDATED"), "H did not update the HUD"
            assert '"10"' in " ".join(texts(p)), "score text did not change to 10"
            p.capture(f"{OUT}/{NAME}.png")
    finally:
        unplace(LEVEL, boot)
        save([LEVEL])
    print("HUD PASS")


if __name__ == "__main__":
    verify(build_boot() if "--verify-only" not in sys.argv else f"{F}/{BOOT}.{BOOT}")
