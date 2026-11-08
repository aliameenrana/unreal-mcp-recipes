#!/usr/bin/env python3
"""Builds and PIE-verifies the weapons recipe: weapon data assets, a hitscan weapon component with
magazine, fire rate and timed reload, damaging BP_HealthComponent through a line trace.

  python3 recipes/weapons/build/weapons.py [--fresh] [--verify-only]

Needs the health recipe built first (/Game/Gameplay/BP_HealthComponent).
"""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, fresh_wipe, PIE, Fail
from bpkit import collision, ensure_bp, create, var, obj_var, defaults, fn, component, data_assets, key, compile_bp, set_props

F = "/Game/Weapons"
D = f"{F}/BP_WeaponDefinition.BP_WeaponDefinition"
W = f"{F}/BP_WeaponComponent.BP_WeaponComponent"
TG = f"{F}/BP_ShootingTarget.BP_ShootingTarget"
T = f"{F}/BP_WeaponTest.BP_WeaponTest"
H = "/Game/Gameplay/BP_HealthComponent.BP_HealthComponent"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
WEAPONS = {"DA_Pistol": {"DisplayName": "Pistol", "Damage": 10.0, "Range": 5000.0, "FireInterval": 0.25,
                         "MagazineSize": 6, "ReloadTime": 1.5},
           "DA_Rifle": {"DisplayName": "Rifle", "Damage": 25.0, "Range": 10000.0, "FireInterval": 0.1,
                        "MagazineSize": 30, "ReloadTime": 2.5}}
V = lambda n: f"(Variables|Default|Get{n})"
WD = lambda n: f"(Class|BPWeaponDefinition|Get{n} :self (Variables|Default|GetWeapon))"
HEALTH_CAST = f'(Utilities|Casting|CastToBP_HealthComponent :Object (Actor|GetComponentbyClass :self {{}} :ComponentClass "{H}_C"))'


def wipe():
    fresh_wipe(LEVEL, [T, TG], [T, TG, W])


def build_definitions():
    ensure_bp(D, "/Script/Engine.PrimaryDataAsset")
    var(D, "DisplayName", "string")
    for n in ("Damage", "Range", "FireInterval", "ReloadTime"):
        var(D, n, "real")
    var(D, "MagazineSize", "int")
    compile_bp(D)
    data_assets(F + "/Data", D + "_C", WEAPONS)


def build_component():
    """Fire() -> Result: 0 fired, 1 fire interval not elapsed, 2 magazine empty, 3 reloading.
    LastHit is true when the shot hit an actor with BP_HealthComponent."""
    create(W, "/Script/Engine.ActorComponent")
    obj_var(W, "Weapon", D + "_C", editable=True)
    var(W, "Ammo", "int")
    var(W, "NextFireAt", "real")
    var(W, "ReloadEndsAt", "real")
    var(W, "LastHit", "bool")
    for d in ("OnFired", "OnReloaded"):
        must("BP", "add_event_dispatcher", {"blueprint": ref(W), "name": d})
    must("BP", "write_graph_dsl", {"graph": W + ":EventGraph", "code": f"""
(event AddEvent|EventBeginPlay
  (Variables|Default|SetAmmo {WD('MagazineSize')}))
(event AddEvent|EventTick (DeltaSeconds)
  (if (and (> {V('ReloadEndsAt')} 0.0) (>= (Utilities|Time|GetGameTimeinSeconds) {V('ReloadEndsAt')}))
    (Variables|Default|SetAmmo {WD('MagazineSize')})
    (Variables|Default|SetReloadEndsAt 0.0)
    (Default|CallOnReloaded)))"""})
    fn(W, "Fire", [], [("Result", "int")], f"""(fn Fire ()
  (bind now (Utilities|Time|GetGameTimeinSeconds))
  (if (> {V('ReloadEndsAt')} 0.0)
    (return 3)
    (else
      (if (< now {V('NextFireAt')})
        (return 1)
        (else
          (if (<= {V('Ammo')} 0)
            (return 2)
            (else
              (Variables|Default|SetAmmo (- {V('Ammo')} 1))
              (Variables|Default|SetNextFireAt (+ now {WD('FireInterval')}))
              (Variables|Default|SetLastHit false)
              (Default|CallOnFired)
              (bind owner (Components|GetOwner :self self))
              (bind fwd (Transformation|GetActorForwardVector :self owner))
              (bind start (+ (Transformation|GetActorLocation :self owner) (* fwd 50.0)))
              (bind (hit ok) (Collision|LineTraceByChannel :Start start :End (+ start (* fwd {WD('Range')}))
                :TraceChannel "TraceTypeQuery1" :bTraceComplex false :bIgnoreSelf true
                :DrawDebugType "ForDuration" :DrawTime 1.0))
              (if ok
                (bind (b1 b2 tm dist loc ipt nrm inrm pm actor comp hbone bone item elem face ts te)
                  (Collision|BreakHitResult hit))
                (Development|PrintString (Utilities|String|Append "WPN_DBG hit " (Utilities|GetDisplayName :Object actor)))
                (bind hc {HEALTH_CAST.format('actor')}
                  (:then
                    (Class|BPHealthComponent|ApplyDamage :self hc :Amount {WD('Damage')})
                    (Variables|Default|SetLastHit true)
                    (return 0))
                  (:CastFailed
                    (return 0)))
                (else
                  (Development|PrintString "WPN_DBG miss")
                  (return 0))))))))))""")
    fn(W, "Reload", [], [("Started", "bool")], f"""(fn Reload ()
  (if (or (> {V('ReloadEndsAt')} 0.0) (>= {V('Ammo')} {WD('MagazineSize')}))
    (return false)
    (else
      (Variables|Default|SetReloadEndsAt (+ (Utilities|Time|GetGameTimeinSeconds) {WD('ReloadTime')}))
      (return true))))""")
    defaults(W, {"Weapon": f"{F}/Data/DA_Pistol.DA_Pistol"})


def build_target():
    create(TG, "/Script/Engine.Actor")
    component(TG, "/Script/Engine.BoxComponent", "Hitbox", {"boxExtent": {"x": 50.0, "y": 50.0, "z": 100.0},
                                                            "bodyInstance": collision("BlockAll")})
    component(TG, "/Script/Engine.StaticMeshComponent", "Visual", {
        "staticMesh": "/Engine/BasicShapes/Cube.Cube", "relativeScale3D": {"x": 1.0, "y": 1.0, "z": 2.0},
        "bodyInstance": collision("NoCollision")})
    component(TG, H + "_C", "Health")
    compile_bp(TG)


def build_test():
    """F: fire. D: fire twice in one frame. Z: empty the magazine and fire. Q: reload and fire in one
    frame. R: print ammo and target health."""
    create(T, "/Script/Engine.Actor")
    component(T, W + "_C", "Weapon")
    obj_var(T, "Target", TG + "_C", editable=True)
    wc = f'(Utilities|Casting|CastToBP_WeaponComponent :Object (Actor|GetComponentbyClass :self self :ComponentClass "{W}_C"))'
    shot = """(Development|PrintString (Utilities|String|Append "WPN_FIRE "
          (Utilities|String|Append (Utilities|String|ToString(Integer) r)
          (Utilities|String|Append " ammo=" (Utilities|String|Append (Utilities|String|ToString(Integer) (Class|BPWeaponComponent|GetAmmo :self wc))
          (Utilities|String|Append " hit=" (Utilities|String|ToString(Boolean) (Class|BPWeaponComponent|GetLastHit :self wc))))))))"""
    with_wc = lambda body: f"""
    (bind wc {wc}
      (:then{body})
      (:CastFailed))"""
    fire = "\n        (bind r (Class|BPWeaponComponent|Fire :self wc))\n        " + shot
    twice = "\n        (Class|BPWeaponComponent|Fire :self wc)" + fire
    empty = "\n        (Class|BPWeaponComponent|SetAmmo :self wc :Ammo 0)" + fire
    reload = "\n        (Class|BPWeaponComponent|Reload :self wc)" + fire
    report = f"""
        (bind hc {HEALTH_CAST.format('(Variables|Default|GetTarget)')}
          (:then (Development|PrintString (Utilities|String|Append "WPN ammo="
            (Utilities|String|Append (Utilities|String|ToString(Integer) (Class|BPWeaponComponent|GetAmmo :self wc))
            (Utilities|String|Append " hp=" (Utilities|String|ToString(Float) (Class|BPHealthComponent|GetHealth :self hc)))))))
          (:CastFailed))"""
    code = '(event AddEvent|EventBeginPlay (Development|PrintString "WPN_READY"))\n(event AddEvent|EventTick (DeltaSeconds)'
    code += key("F", with_wc(fire)) + key("D", with_wc(twice)) + key("Z", with_wc(empty))
    code += key("Q", with_wc(reload)) + key("R", with_wc(report)) + ")"
    must("BP", "write_graph_dsl", {"graph": T + ":EventGraph", "code": code})
    compile_bp(T)


def verify():
    # L_OcclusionTest has occluder meshes near the ground; Z=2000 keeps the firing lane clear.
    test = place(LEVEL, T, "WeaponTest", (0, 0, 2000))
    target = place(LEVEL, TG, "ShootingTarget", (600, 0, 2000))
    set_props(test, {"Target": target["refPath"]}, "WeaponTest")
    try:
        with PIE() as p:
            time.sleep(2)
            assert "WPN_READY" in p.markers("WPN_READY"), "test actor did not start"

            def last(tag):
                got = p.markers(tag)
                return got.rsplit(tag, 1)[1].split('"')[0].strip()

            def press(k, first=False):
                n = p.markers("WPN_FIRE").count("WPN_FIRE")
                p.key(k, focus_game=first)
                assert p.markers("WPN_FIRE").count("WPN_FIRE") > n, f"{k}: no fire result"
                return last("WPN_FIRE ")

            def state():
                n = p.markers("WPN ammo=").count("WPN ammo=")
                p.key("R", focus_game=False)
                assert p.markers("WPN ammo=").count("WPN ammo=") > n, "no state print"
                ammo, hp = last("WPN ammo=").split(" hp=")
                return int(ammo), float(hp)

            def expect(k, want, first=False):
                got = press(k, first)
                assert got == want, f"{k}: got '{got}', wanted '{want}' {p.markers('WPN_DBG')[-300:]}"
                print(f"  {k}: {got}")

            expect("F", "0 ammo=5 hit=true", True)
            expect("D", "1 ammo=4 hit=true")
            assert state() == (4, 80.0), f"after two hits: {state()}"
            expect("Z", "2 ammo=0 hit=true")
            expect("Q", "3 ammo=0 hit=true")
            time.sleep(3)
            assert state()[0] == 6, f"magazine after reload: {state()}"
            expect("F", "0 ammo=5 hit=true")
            ammo, hp = state()
            assert hp == 70.0, f"target hp {hp}"
            print(f"  reload refilled to 6; target hp 100 -> {hp}")
    finally:
        unplace(LEVEL, T)
        unplace(LEVEL, TG)
        save([LEVEL])
    print("WEAPONS PASS")


if __name__ == "__main__":
    mcp.init()
    if not must("Asset", "exists", {"path": H}):
        raise Fail("build the health recipe first: python3 recipes/health/build/health.py")
    if "--verify-only" not in sys.argv:
        if "--fresh" in sys.argv:
            wipe()
        build_definitions()
        build_component()
        build_target()
        build_test()
        save([x.split(".")[0] for x in (D, W, TG, T)] + [f"{F}/Data/{n}" for n in WEAPONS])
    verify()
