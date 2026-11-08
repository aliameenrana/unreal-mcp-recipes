#!/usr/bin/env python3
"""Builds and PIE-verifies the magic recipe: spell data assets, a caster component with mana,
regen and per-spell cooldowns, a projectile that damages BP_HealthComponent, and a target dummy.

  python3 recipes/magic/build/magic.py [--fresh] [--verify-only]

Needs the health recipe built first (/Game/Gameplay/BP_HealthComponent).
"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, ensure_level, delete_assets, PIE, Fail

F = "/Game/Magic"
D = f"{F}/BP_SpellDefinition.BP_SpellDefinition"
C = f"{F}/BP_SpellCaster.BP_SpellCaster"
PR = f"{F}/BP_SpellProjectile.BP_SpellProjectile"
TG = f"{F}/BP_MagicTarget.BP_MagicTarget"
T = f"{F}/BP_MagicTest.BP_MagicTest"
H = "/Game/Gameplay/BP_HealthComponent.BP_HealthComponent"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
SPELLS = {"DA_Fireball": {"DisplayName": "Fireball", "ManaCost": 30.0, "Cooldown": 2.0, "Damage": 25.0},
          "DA_Frostbolt": {"DisplayName": "Frostbolt", "ManaCost": 10.0, "Cooldown": 0.5, "Damage": 10.0}}
V = lambda n: f"(Variables|Default|Get{n})"
FRESH = "--fresh" in sys.argv


def create(path, parent):
    folder, name = path.rsplit("/", 1)[0], path.rsplit(".", 1)[1]
    must("BP", "create", {"folder_path": folder, "asset_name": name, "asset_type": ref(parent)})


def var(bp, n, t, container=None):
    must("BP", "add_variable", {"blueprint": ref(bp), "name": n, "type_name": t, "graph": None, "container_type": container})


def defaults(bp, values):
    """Variable defaults live on the class default object; there is no per-variable default tool."""
    must("BP", "compile_blueprint", {"blueprint": ref(bp)})
    cdo = must("BP", "get_default_object", {"blueprint": ref(bp)})
    must("Object", "set_properties", {"instance": cdo, "values": json.dumps(values)})
    got = json.loads(must("Object", "get_properties", {"instance": cdo, "properties": list(values)}))
    if got != values:
        raise Fail(f"{bp} defaults {got}, wanted {values}")


def fn(bp, name, params, outputs, code):
    g = must("BP", "add_function_graph", {"blueprint": ref(bp), "graph_name": name})
    for io, plist in ((True, params), (False, outputs)):
        for pn, pt in plist:
            if pt.endswith("_C"):
                must("BP", "add_object_function_param", {"graph": g, "param_name": pn, "object_class": ref(pt),
                                                         "input_param": io, "container_type": None})
            else:
                must("BP", "add_function_param", {"graph": g, "param_name": pn, "param_type": pt,
                                                  "input_param": io, "container_type": None})
    must("BP", "write_graph_dsl", {"graph": f"{bp}:{name}", "code": code})


def component(owner, cls, name, props=None):
    c = must("Actor", "add_component", {"owner": ref(owner), "component_type": ref(cls), "name": name})
    if props:
        must("Object", "set_properties", {"instance": c, "values": json.dumps(props)})
        got = json.loads(must("Object", "get_properties", {"instance": c, "properties": list(props)}))
        for k, v in props.items():
            if isinstance(v, (int, float)) and abs(got[k] - v) > 1e-3:
                raise Fail(f"{name}.{k} = {got[k]}, wanted {v}")
    return c


def wipe():
    ensure_level(LEVEL)
    for p in (T, TG):
        unplace(LEVEL, p)
    save([LEVEL])
    delete_assets([T, TG, PR, C] + [f"{F}/Spells/{n}.{n}" for n in SPELLS] + [D])


def build_spells():
    create(D, "/Script/Engine.PrimaryDataAsset")
    var(D, "DisplayName", "string")
    for n in ("ManaCost", "Cooldown", "Damage"):
        var(D, n, "real")
    must("BP", "compile_blueprint", {"blueprint": ref(D)})
    for n, vals in SPELLS.items():
        must("DataAsset", "create", {"folder_path": F + "/Spells", "asset_name": n, "asset_type": ref(D + "_C")})
        inst = ref(f"{F}/Spells/{n}.{n}")
        must("Object", "set_properties", {"instance": inst, "values": json.dumps(vals)})
        got = json.loads(must("Object", "get_properties", {"instance": inst, "properties": list(vals)}))
        assert got == vals, f"{n}: {got}"


def build_projectile():
    create(PR, "/Script/Engine.Actor")
    component(PR, "/Script/Engine.SphereComponent", "Collision", {"sphereRadius": 16.0})
    component(PR, "/Script/Engine.StaticMeshComponent", "Visual", {
        "staticMesh": "/Engine/BasicShapes/Sphere.Sphere", "relativeScale3D": {"x": 0.3, "y": 0.3, "z": 0.3},
        "bodyInstance": {"collisionProfileName": "NoCollision"}})
    component(PR, "/Script/Engine.ProjectileMovementComponent", "Movement",
              {"initialSpeed": 1500.0, "maxSpeed": 1500.0, "projectileGravityScale": 0.0})
    var(PR, "Damage", "real")
    # Overlap, not hit: the projectile passes through actors without health (the player pawn).
    must("BP", "write_graph_dsl", {"graph": PR + ":EventGraph", "code": f"""
(event AddEvent|EventBeginPlay
  (Actor|SetLifeSpan :self self :InLifespan 3.0))
(event AddEvent|Collision|EventActorBeginOverlap (OtherActor)
  (bind hc (Utilities|Casting|CastToBP_HealthComponent
      :Object (Actor|GetComponentbyClass :self OtherActor :ComponentClass "{H}_C"))
    (:then
      (Class|BPHealthComponent|ApplyDamage :self hc :Amount {V('Damage')})
      (Development|PrintString "MAG_HIT")
      (Actor|DestroyActor :self self))
    (:CastFailed)))"""})
    must("BP", "compile_blueprint", {"blueprint": ref(PR)})


def build_caster():
    """TryCast(Spell) -> Result: 0 cast, 1 on cooldown, 2 not enough mana."""
    create(C, "/Script/Engine.ActorComponent")
    for n in ("MaxMana", "Mana", "ManaRegen"):
        var(C, n, "real")
    must("BP", "add_object_variable", {"blueprint": ref(C), "name": "Spells", "object_class": ref(D + "_C"),
                                       "graph": None, "container_type": "ARRAY"})
    var(C, "ReadyAt", "real", "ARRAY")
    must("BP", "add_event_dispatcher", {"blueprint": ref(C), "name": "OnManaChanged"})
    must("BP", "write_graph_dsl", {"graph": C + ":EventGraph", "code": f"""
(event AddEvent|EventBeginPlay
  (Variables|Default|SetMana {V('MaxMana')}))
(event AddEvent|EventTick (DeltaSeconds)
  (if (< {V('Mana')} {V('MaxMana')})
    (Variables|Default|SetMana (Math|Float|Min(Float) {V('MaxMana')} (+ {V('Mana')} (* {V('ManaRegen')} DeltaSeconds))))
    (Default|CallOnManaChanged)))"""})
    fn(C, "TryCast", [("Spell", D + "_C")], [("Result", "int")], f"""(fn TryCast (Spell)
  (if (< (Utilities|Array|FindItem {V('Spells')} Spell) 0)
    (Utilities|Array|Add {V('Spells')} Spell)
    (Utilities|Array|Add {V('ReadyAt')} 0.0))
  (bind i (Utilities|Array|FindItem {V('Spells')} Spell))
  (bind now (Utilities|Time|GetGameTimeinSeconds))
  (if (< now (Utilities|Array|Get(acopy) {V('ReadyAt')} i))
    (return 1)
    (else
      (if (< {V('Mana')} (Class|BPSpellDefinition|GetManaCost :self Spell))
        (return 2)
        (else
          (Variables|Default|SetMana (- {V('Mana')} (Class|BPSpellDefinition|GetManaCost :self Spell)))
          (Utilities|Array|SetArrayElem {V('ReadyAt')} i (+ now (Class|BPSpellDefinition|GetCooldown :self Spell)))
          (Default|CallOnManaChanged)
          (bind owner (Components|GetOwner :self self))
          (bind proj (Game|SpawnActorfromClass
            :Class "{PR}_C"
            :SpawnTransform (Math|Transform|MakeTransform
              :Location (+ (Transformation|GetActorLocation :self owner)
                           (* (Transformation|GetActorForwardVector :self owner) 100.0))
              :Rotation (Transformation|GetActorRotation :self owner))
            :CollisionHandlingOverride "AlwaysSpawn"
            :Owner owner))
          (Class|BPSpellProjectile|SetDamage :self proj :Damage (Class|BPSpellDefinition|GetDamage :self Spell))
          (return 0))))))""")
    defaults(C, {"MaxMana": 100.0, "ManaRegen": 10.0})


def build_target():
    create(TG, "/Script/Engine.Actor")
    component(TG, "/Script/Engine.BoxComponent", "Hitbox", {"boxExtent": {"x": 50.0, "y": 50.0, "z": 100.0}})
    component(TG, "/Script/Engine.StaticMeshComponent", "Visual", {
        "staticMesh": "/Engine/BasicShapes/Cylinder.Cylinder", "relativeScale3D": {"x": 1.0, "y": 1.0, "z": 2.0},
        "bodyInstance": {"collisionProfileName": "NoCollision"}})
    component(TG, H + "_C", "Health")
    must("BP", "compile_blueprint", {"blueprint": ref(TG)})


def key(k, body):
    return f"""
  (if (Game|Player|WasInputKeyJustPressed :self (Game|GetPlayerController 0) :Key "{k}"){body})"""


def build_test():
    """F: Fireball. G: Frostbolt. M: set mana to 5 and cast Frostbolt (cost 10) in the same frame.
    R: print mana and target health."""
    create(T, "/Script/Engine.Actor")
    component(T, C + "_C", "Caster")
    must("BP", "add_object_variable", {"blueprint": ref(T), "name": "Target", "object_class": ref(TG + "_C"),
                                       "graph": None, "container_type": None})
    must("BP", "set_variable_instance_editable", {"blueprint": ref(T), "variable_name": "Target", "instance_editable": True})
    caster = f'(Actor|GetComponentbyClass :self self :ComponentClass "{C}_C")'
    cast = lambda spell: f"""
    (bind cc (Utilities|Casting|CastToBP_SpellCaster :Object {caster})
      (:then
        (bind r (Class|BPSpellCaster|TryCast :self cc :Spell "{F}/Spells/{spell}.{spell}"))
        (Development|PrintString (Utilities|String|Append "MAG_CAST "
          (Utilities|String|Append (Utilities|String|ToString(Integer) r)
            (Utilities|String|Append " mana=" (Utilities|String|ToString(Float) (Class|BPSpellCaster|GetMana :self cc)))))))
      (:CastFailed))"""
    drain = f"""
    (bind cc (Utilities|Casting|CastToBP_SpellCaster :Object {caster})
      (:then
        (Class|BPSpellCaster|SetMana :self cc :Mana 5.0)
        (bind r (Class|BPSpellCaster|TryCast :self cc :Spell "{F}/Spells/DA_Frostbolt.DA_Frostbolt"))
        (Development|PrintString (Utilities|String|Append "MAG_CAST "
          (Utilities|String|Append (Utilities|String|ToString(Integer) r)
            (Utilities|String|Append " mana=" (Utilities|String|ToString(Float) (Class|BPSpellCaster|GetMana :self cc)))))))
      (:CastFailed))"""
    hp = f'(Actor|GetComponentbyClass :self (Variables|Default|GetTarget) :ComponentClass "{H}_C")'
    report = f"""
    (bind cc (Utilities|Casting|CastToBP_SpellCaster :Object {caster})
      (:then
        (bind hc (Utilities|Casting|CastToBP_HealthComponent :Object {hp})
          (:then (Development|PrintString (Utilities|String|Append "MAG mana="
            (Utilities|String|Append (Utilities|String|ToString(Float) (Class|BPSpellCaster|GetMana :self cc))
              (Utilities|String|Append " hp=" (Utilities|String|ToString(Float) (Class|BPHealthComponent|GetHealth :self hc)))))))
          (:CastFailed)))
      (:CastFailed))"""
    code = '(event AddEvent|EventBeginPlay (Development|PrintString "MAG_READY"))\n(event AddEvent|EventTick (DeltaSeconds)'
    code += key("F", cast("DA_Fireball")) + key("G", cast("DA_Frostbolt")) + key("M", drain) + key("R", report) + ")"
    must("BP", "write_graph_dsl", {"graph": T + ":EventGraph", "code": code})
    must("BP", "compile_blueprint", {"blueprint": ref(T)})


def verify():
    test = place(LEVEL, T, "MagicTest", (0, 0, 150))
    target = place(LEVEL, TG, "MagicTarget", (600, 0, 150))
    must("Object", "set_properties", {"instance": test, "values": json.dumps({"Target": target["refPath"]})})
    assert "MagicTarget" in must("Object", "get_properties", {"instance": test, "properties": ["Target"]})
    try:
        with PIE() as p:
            time.sleep(2)
            assert "MAG_READY" in p.markers("MAG_READY"), "test actor did not start"

            def last(tag):
                got = p.markers(tag)
                return got.rsplit(tag, 1)[1].split('"')[0].strip() if tag in got else None

            def press(k, first=False):
                n = p.markers("MAG_CAST").count("MAG_CAST")
                p.key(k, focus_game=first)
                assert p.markers("MAG_CAST").count("MAG_CAST") > n, f"{k}: no cast result"
                r, mana = last("MAG_CAST ").split(" mana=")
                return r, float(mana)

            def state():
                n = p.markers("MAG mana=").count("MAG mana=")
                p.key("R", focus_game=False)
                assert p.markers("MAG mana=").count("MAG mana=") > n, "no state print"
                mana, hp = last("MAG mana=").split(" hp=")
                return float(mana), float(hp)

            t0 = time.time()
            r, mana = press("F", True)
            assert r == "0", f"first fireball result {r}"
            assert 70.0 <= mana < 71.0, f"mana right after fireball {mana}, wanted 70"
            r, _ = press("F")
            gap = time.time() - t0
            assert r == "1", f"second fireball {gap:.1f}s later gave {r}, wanted 1 (cooldown 2s)"
            print(f"  cooldown: rejected {gap:.1f}s after cast")
            time.sleep(1)
            assert "MAG_HIT" in p.markers("MAG_HIT"), "projectile did not hit the target"
            _, hp = state()
            assert hp == 75.0, f"target hp after fireball {hp}"
            print(f"  fireball: mana 100 -> {mana:.1f}, target hp 100 -> {hp}")
            r, mana = press("M")
            assert r == "2" and mana == 5.0, f"frostbolt with 5 mana gave {r} (mana {mana}), wanted 2"
            print("  mana: rejected")
            m1, _ = state()
            time.sleep(2)
            m2, _ = state()
            assert m2 > m1 + 5, f"no regen: {m1} -> {m2}"
            print(f"  regen: {m1:.1f} -> {m2:.1f}")
            hits = p.markers("MAG_HIT").count("MAG_HIT")
            r, mana = press("G")
            assert r == "0", f"frostbolt gave {r} (mana {mana})"
            time.sleep(1)
            assert p.markers("MAG_HIT").count("MAG_HIT") > hits, "frostbolt did not hit"
            _, hp = state()
            assert hp == 65.0, f"target hp after frostbolt {hp}"
            print(f"  frostbolt: target hp -> {hp}")
    finally:
        unplace(LEVEL, T)
        unplace(LEVEL, TG)
        save([LEVEL])
    print("MAGIC PASS")


if __name__ == "__main__":
    mcp.init()
    if not must("Asset", "exists", {"path": H}):
        raise Fail("build the health recipe first: python3 recipes/health/build/health.py")
    if "--verify-only" not in sys.argv:
        if FRESH:
            wipe()
        build_spells()
        build_projectile()
        build_caster()
        build_target()
        build_test()
        save([x.split(".")[0] for x in (D, PR, C, TG, T)] + [f"{F}/Spells/{n}" for n in SPELLS])
    verify()
