#!/usr/bin/env python3
"""Builds and PIE-verifies BP_HealthComponent and BP_ScoreComponent.

  python3 recipes/health/build/health.py [--fresh] [--verify-only]
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, fresh_wipe, PIE, Fail

F = "/Game/Gameplay"
H = f"{F}/BP_HealthComponent.BP_HealthComponent"
S = f"{F}/BP_ScoreComponent.BP_ScoreComponent"
T = f"{F}/BP_HealthTest.BP_HealthTest"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
V = lambda n: f"(Variables|Default|Get{n})"


def var(bp, n, t):
    must("BP", "add_variable", {"blueprint": ref(bp), "name": n, "type_name": t, "graph": None, "container_type": None})


def fn(bp, name, params, code):
    g = must("BP", "add_function_graph", {"blueprint": ref(bp), "graph_name": name})
    for pn, pt in params:
        must("BP", "add_function_param", {"graph": g, "param_name": pn, "param_type": pt,
                                          "input_param": True, "container_type": None})
    must("BP", "write_graph_dsl", {"graph": f"{bp}:{name}", "code": code})


def create(path, parent):
    folder, name = path.rsplit("/", 1)[0], path.rsplit(".", 1)[1]
    must("BP", "create", {"folder_path": folder, "asset_name": name, "asset_type": ref(parent)})


def build_health():
    create(H, "/Script/Engine.ActorComponent")
    for n, t in (("MaxHealth", "real"), ("Health", "real"), ("bDead", "bool"),
                 ("DotPerSecond", "real"), ("DotRemaining", "real")):
        var(H, n, t)
    for d in ("OnHealthChanged", "OnDeath"):
        must("BP", "add_event_dispatcher", {"blueprint": ref(H), "name": d})
    # Bool variables lose their b prefix in node IDs: bDead -> GetDead / SetDead.
    fn(H, "ApplyDamage", [("Amount", "real")], f"""(fn ApplyDamage (Amount)
  (if (not {V('Dead')})
    (bind h (Math|Float|Clamp(Float) (- {V('Health')} Amount) 0.0 {V('MaxHealth')}))
    (Variables|Default|SetHealth h)
    (Default|CallOnHealthChanged)
    (if (<= h 0.0)
      (Variables|Default|SetDead true)
      (Variables|Default|SetDotRemaining 0.0)
      (Default|CallOnDeath))))""")
    fn(H, "Heal", [("Amount", "real")], f"""(fn Heal (Amount)
  (if (not {V('Dead')})
    (Variables|Default|SetHealth (Math|Float|Clamp(Float) (+ {V('Health')} Amount) 0.0 {V('MaxHealth')}))
    (Default|CallOnHealthChanged)))""")
    fn(H, "ApplyDamageOverTime", [("PerSecond", "real"), ("Duration", "real")], """(fn ApplyDamageOverTime (PerSecond Duration)
  (Variables|Default|SetDotPerSecond PerSecond)
  (Variables|Default|SetDotRemaining Duration))""")
    must("BP", "write_graph_dsl", {"graph": H + ":EventGraph", "code": f"""
(event AddEvent|EventBeginPlay
  (Variables|Default|SetHealth {V('MaxHealth')})
  (Variables|Default|SetDead false))
(event AddEvent|EventTick (DeltaSeconds)
  ; bind on a pure getter is not a snapshot: every reader re-runs the getter. Damage is applied
  ; before DotRemaining changes so dt still sees the old value.
  (bind rem {V('DotRemaining')})
  (if (> rem 0.0)
    (bind dt (Math|Float|Min(Float) DeltaSeconds rem))
    (CallFunction|ApplyDamage :Amount (* {V('DotPerSecond')} dt))
    (Variables|Default|SetDotRemaining (Math|Float|Max(Float) 0.0 (- rem dt)))))"""})
    must("BP", "compile_blueprint", {"blueprint": ref(H)})
    cdo = ref(f"{F}/BP_HealthComponent.Default__BP_HealthComponent_C")
    must("Object", "set_properties", {"instance": cdo, "values": '{"MaxHealth": 100.0}'})
    assert '"MaxHealth":100' in must("Object", "get_properties", {"instance": cdo, "properties": ["MaxHealth"]})


def build_score():
    create(S, "/Script/Engine.ActorComponent")
    var(S, "Score", "int")
    must("BP", "add_event_dispatcher", {"blueprint": ref(S), "name": "OnScoreChanged"})
    fn(S, "AddScore", [("Points", "int")], f"""(fn AddScore (Points)
  (Variables|Default|SetScore (+ {V('Score')} Points))
  (Default|CallOnScoreChanged))""")
    must("BP", "compile_blueprint", {"blueprint": ref(S)})


if __name__ == "__main__":
    mcp.init()
    if "--fresh" in sys.argv:
        # Magic, weapons and inventory reference these classes; rebuild them with --fresh afterwards.
        fresh_wipe(LEVEL, [T], [T, S, H])
    if "--verify-only" not in sys.argv:
        build_health()
        build_score()
        save([H.split(".")[0], S.split(".")[0]])
    print("components built")


def key(k, body):
    return f'''
  (if (Game|Player|WasInputKeyJustPressed :self pc :Key "{k}"){body})'''


def build_test():
    """Test actor: K damage 30, J heal 10, L 25/s for 2 s, O +10 score, R prints state."""
    create(T, "/Script/Engine.Actor")
    for comp, cls in (("HealthComp", H), ("ScoreComp", S)):
        must("Actor", "add_component", {"owner": ref(T), "component_type": ref(cls + "_C"), "name": comp})
    hc, sc = "(Variables|Default|GetHealthComp)", "(Variables|Default|GetScoreComp)"
    must("BP", "write_graph_dsl", {"graph": T + ":EventGraph", "code": f"""
(event AddEvent|EventBeginPlay
  (Input|EnableInput :self self :PlayerController (Game|GetPlayerController 0))
  (Development|PrintString "HT_READY"))
(event AddEvent|EventTick (DeltaSeconds)
  (bind pc (Game|GetPlayerController 0))
  {key("K", f" (Class|BPHealthComponent|ApplyDamage :self {hc} :Amount 30.0)")}
  {key("J", f" (Class|BPHealthComponent|Heal :self {hc} :Amount 10.0)")}
  {key("L", f" (Class|BPHealthComponent|ApplyDamageOverTime :self {hc} :PerSecond 25.0 :Duration 2.0)")}
  {key("O", f" (Class|BPScoreComponent|AddScore :self {sc} :Points 10)")}
  {key("R", f''' (Development|PrintString (Utilities|String|Append "HT hp="
      (Utilities|String|Append (Utilities|String|ToString(Float) (Class|BPHealthComponent|GetHealth :self {hc}))
      (Utilities|String|Append " dead="
      (Utilities|String|Append (Utilities|String|ToString(Boolean) (Class|BPHealthComponent|GetDead :self {hc}))
      (Utilities|String|Append " score=" (Utilities|String|ToString(Integer) (Class|BPScoreComponent|GetScore :self {sc}))))))))''')})
"""})
    save([T.split(".")[0]])


def verify():
    place(LEVEL, T, "HealthTest")
    try:
        with PIE() as p:
            time.sleep(2)
            assert "HT_READY" in p.markers("HT_READY"), "test actor did not start"
            steps = [("R", None, "hp=100.0 dead=false score=0"),
                     ("K", None, "hp=70.0 dead=false"), ("J", None, "hp=80.0 dead=false"),
                     ("L", 8.0, "hp=30.0 dead=false"), ("O", None, "score=10"),
                     ("K", None, "hp=0.0 dead=true"), ("J", None, "hp=0.0 dead=true")]
            first = True
            for k, wait, want in steps:
                p.key(k, focus_game=first)
                first = False
                if wait:
                    time.sleep(wait)
                n = p.markers("HT hp=").count("HT hp=")
                p.key("R", focus_game=False)
                got = p.markers("HT hp=")
                assert got.count("HT hp=") > n, f"after {k}: no state print"
                last = got.rsplit("HT hp=", 1)[1]
                state = dict(kv.split("=") for kv in ("hp=" + last.split('"')[0]).split())
                for kv in want.split():
                    wk, wv = kv.split("=")
                    ok = abs(float(state[wk]) - float(wv)) < 0.5 if wk == "hp" else state[wk] == wv
                    assert ok, f"after {k}: want {want}, got {state}"
                print(f"  {k}: hp={last.split(chr(34))[0]}")
    finally:
        unplace(LEVEL, T)
        save([LEVEL])
    print("HEALTH PASS")


if __name__ == "__main__":
    if "--verify-only" not in sys.argv:
        build_test()
    verify()
