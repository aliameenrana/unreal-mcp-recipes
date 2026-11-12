#!/usr/bin/env python3
"""Builds and PIE-verifies the enemy AI recipe: a mannequin Character that patrols, sees a target
within SightRange through a clear line trace, chases it, and attacks BP_HealthComponent in AttackRange.
The animation is swapped by state (single-node mode) and a weapon mesh is attached to the hand_r socket.

  python3 recipes/enemy/build/enemy.py [--fresh] [--verify-only]

Needs the health recipe built first (/Game/Gameplay/BP_HealthComponent).
"""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, fresh_wipe, PIE, Fail
from bpkit import collision, create, var, obj_var, fn, component, key, compile_bp, set_props

F = "/Game/Enemy"
E = f"{F}/BP_Enemy.BP_Enemy"
TG = f"{F}/BP_EnemyTarget.BP_EnemyTarget"
WL = f"{F}/BP_EnemyWall.BP_EnemyWall"
AR = f"{F}/BP_EnemyArena.BP_EnemyArena"
T = f"{F}/BP_EnemyTest.BP_EnemyTest"
H = "/Game/Gameplay/BP_HealthComponent.BP_HealthComponent"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
MANNY = "/Game/Characters/Mannequins"
MESH = f"{MANNY}/Meshes/SKM_Manny_Simple.SKM_Manny_Simple"
ANIMS = {"IdleAnim": f"{MANNY}/Anims/Unarmed/MM_Idle.MM_Idle",
         "ChaseAnim": f"{MANNY}/Anims/Unarmed/Jog/MF_Unarmed_Jog_Fwd.MF_Unarmed_Jog_Fwd",
         "AttackAnim": f"{MANNY}/Anims/Unarmed/Attack/MM_Attack_01.MM_Attack_01"}
SOCKET = "hand_r"
TUNING = {"SightRange": 1500.0, "AttackRange": 200.0, "AttackDamage": 10.0, "AttackInterval": 1.0}
# Z=4000 keeps the arena clear of L_OcclusionTest's occluders; the floor top is at Z=4010.
Z, FLOOR_TOP = 4000.0, 4010.0
STAND = FLOOR_TOP + 90.0
V = lambda n: f"(Variables|Default|Get{n})"
HEALTH_CAST = f'(Utilities|Casting|CastToBP_HealthComponent :Object (Actor|GetComponentbyClass :self {{}} :ComponentClass "{H}_C"))'
HIT = "(b1 b2 tm dist loc ipt nrm inrm pm actor comp hbone bone item elem face ts te)"


def wipe():
    fresh_wipe(LEVEL, [T, E, TG, WL, AR], [T, E, TG, WL, AR])


def box_actor(path, extent, mesh_scale, health=False):
    create(path, "/Script/Engine.Actor")
    component(path, "/Script/Engine.BoxComponent", "Box", {"boxExtent": extent, "bodyInstance": collision("BlockAll")})
    component(path, "/Script/Engine.StaticMeshComponent", "Visual", {
        "staticMesh": "/Engine/BasicShapes/Cube.Cube", "relativeScale3D": mesh_scale,
        "bodyInstance": collision("NoCollision")})
    if health:
        component(path, H + "_C", "Health")
    compile_bp(path)


def build_props():
    box_actor(AR, {"x": 1500.0, "y": 1500.0, "z": 10.0}, {"x": 30.0, "y": 30.0, "z": 0.2})
    box_actor(TG, {"x": 50.0, "y": 50.0, "z": 100.0}, {"x": 1.0, "y": 1.0, "z": 2.0}, health=True)
    box_actor(WL, {"x": 20.0, "y": 300.0, "z": 200.0}, {"x": 0.4, "y": 6.0, "z": 4.0})


def build_enemy():
    """State: 0 patrol, 1 chase, 2 attack. Think() refreshes perception, state and animation in one
    call, so a caller can read the result in the same frame."""
    create(E, "/Script/Engine.Character")
    obj_var(E, "Target", "/Script/Engine.Actor", editable=True)
    for n in TUNING:
        var(E, n, "real")
    for n in ("NextAttackAt", "PatrolSign"):
        var(E, n, "real")
    for n in ("InAttackRange", "CanSeeTarget"):
        var(E, n, "bool")
    for n in ("State", "AnimState"):
        var(E, n, "int")
    var(E, "Home", "vector")
    var(E, "PatrolOffset", "vector")
    for n in list(ANIMS) + ["CurrentAnim"]:
        obj_var(E, n, "/Script/Engine.AnimSequence")
    component(E, "/Script/Engine.StaticMeshComponent", "Weapon", {
        "staticMesh": "/Engine/BasicShapes/Cube.Cube", "relativeScale3D": {"x": 0.05, "y": 0.05, "z": 0.8},
        "bodyInstance": collision("NoCollision")})

    # The trace stops on the first blocking actor; only the target carries BP_HealthComponent, so a
    # successful cast on the hit actor means nothing stands between the enemy and the target.
    fn(E, "Perceive", [], [], f"""(fn Perceive ()
  (bind t {V('Target')})
  (bind d (Transformation|GetDistanceTo :self self :OtherActor t))
  (Variables|Default|SetInAttackRange (<= d {V('AttackRange')}))
  (Variables|Default|SetCanSeeTarget false)
  (if (<= d {V('SightRange')})
    (bind eye (+ (Transformation|GetActorLocation :self self) (Math|Vector|MakeVector 0.0 0.0 60.0)))
    (bind (hit ok) (Collision|LineTraceByChannel :Start eye :End (Transformation|GetActorLocation :self t)
      :TraceChannel "TraceTypeQuery1" :bTraceComplex false :bIgnoreSelf true :DrawDebugType "None" :DrawTime 0.0))
    (if ok
      (bind {HIT} (Collision|BreakHitResult hit))
      (bind hc {HEALTH_CAST.format('actor')}
        (:then (Variables|Default|SetCanSeeTarget true))
        (:CastFailed)))))""")

    fn(E, "DecideState", [], [], f"""(fn DecideState ()
  (if {V('CanSeeTarget')}
    (if {V('InAttackRange')}
      (Variables|Default|SetState 2)
      (else (Variables|Default|SetState 1)))
    (else (Variables|Default|SetState 0))))""")

    play = lambda a: f"""
        (Components|Animation|PlayAnimation :self (Variables|Character|GetMesh) :NewAnimToPlay {V(a)} :bLooping true)
        (Variables|Default|SetCurrentAnim {V(a)})"""
    fn(E, "ApplyAnim", [], [], f"""(fn ApplyAnim ()
  (bind s {V('State')})
  (if (!= s {V('AnimState')})
    (Variables|Default|SetAnimState s)
    (if (== s 0){play('IdleAnim')}
      (else
        (if (== s 1){play('ChaseAnim')}
          (else{play('AttackAnim')}))))))""")

    compile_bp(E)  # a function is callable as CallFunction|<Name> only after a compile
    fn(E, "Think", [], [], """(fn Think ()
  (CallFunction|Perceive)
  (CallFunction|DecideState)
  (CallFunction|ApplyAnim))""")

    # CharacterMovement clamps input to length 1 and drops Z while walking, so raw offsets work as directions.
    fn(E, "Act", [], [], f"""(fn Act ()
  (bind s {V('State')})
  (bind here (Transformation|GetActorLocation :self self))
  (if (== s 1)
    (Pawn|Input|AddMovementInput :self self :WorldDirection (- (Transformation|GetActorLocation :self {V('Target')}) here) :ScaleValue 1.0 :bForce false)
    (else
      (if (== s 2)
        (bind now (Utilities|Time|GetGameTimeinSeconds))
        (if (>= now {V('NextAttackAt')})
          (Variables|Default|SetNextAttackAt (+ now {V('AttackInterval')}))
          (bind hc {HEALTH_CAST.format(V('Target'))}
            (:then
              (Class|BPHealthComponent|ApplyDamage :self hc :Amount {V('AttackDamage')})
              (Development|PrintString "ENEMY_ATTACK"))
            (:CastFailed)))
        (else
          (bind goal (+ {V('Home')} (* {V('PatrolOffset')} {V('PatrolSign')})))
          (if (< (Math|Vector|VectorLengthXY (- goal here)) 50.0)
            (Variables|Default|SetPatrolSign (- 1.0 {V('PatrolSign')}))
            (else
              (Pawn|Input|AddMovementInput :self self :WorldDirection (- goal here) :ScaleValue 1.0 :bForce false))))))))""")

    must("BP", "write_graph_dsl", {"graph": E + ":EventGraph", "code": f"""
(event AddEvent|EventBeginPlay
  (bind mesh (Variables|Character|GetMesh))
  (Transformation|SetRelativeLocationAndRotation :self mesh :NewLocation (Math|Vector|MakeVector 0.0 0.0 -90.0)
    :NewRotation (Math|Rotator|MakeRotator 0.0 0.0 -90.0) :bSweep false :bTeleport true)
  (Components|Animation|SetAnimationMode :self mesh :InAnimationMode "AnimationSingleNode" :bForceInitAnimScriptInstance false)
  (Transformation|AttachComponentToComponent :self (Variables|Default|GetWeapon) :Parent mesh :SocketName "{SOCKET}"
    :LocationRule "SnapToTarget" :RotationRule "SnapToTarget" :ScaleRule "KeepWorld" :bWeldSimulatedBodies false)
  (Variables|Default|SetHome (Transformation|GetActorLocation :self self))
  (Variables|Default|SetAnimState -1)
  (Development|PrintString (Utilities|String|Append "ENEMY_READY socket="
    (Utilities|String|Append (Utilities|String|ToString(Boolean) (Transformation|DoesSocketExist :self mesh :InSocketName "{SOCKET}"))
    (Utilities|String|Append " at=" (Utilities|String|ToString(Name) (Transformation|GetAttachSocketName :self (Variables|Default|GetWeapon))))))))
(event AddEvent|EventTick (DeltaSeconds)
  (CallFunction|Think)
  (CallFunction|Act))"""})

    compile_bp(E)
    cdo = must("BP", "get_default_object", {"blueprint": ref(E)})
    set_props(cdo, dict(TUNING, PatrolSign=1.0, PatrolOffset={"x": 400.0, "y": 0.0, "z": 0.0},
                        bUseControllerRotationYaw=False, **ANIMS), "BP_Enemy")
    comps = json.loads(must("Object", "get_properties", {"instance": cdo, "properties": ["Mesh", "CharacterMovement"]}))
    set_props(comps["Mesh"], {"skeletalMesh": MESH}, "Mesh")
    set_props(comps["CharacterMovement"], {"maxWalkSpeed": 300.0, "bOrientRotationToMovement": True}, "CharacterMovement")
    compile_bp(E)


def build_test():
    """One..Four put the target out of sight range, in chase range, in attack range, and in chase range
    behind a wall; each resets the enemy to its start and calls Think. R prints the enemy's state."""
    create(T, "/Script/Engine.Actor")
    obj_var(T, "Enemy", E + "_C", editable=True)
    obj_var(T, "Target", TG + "_C", editable=True)
    obj_var(T, "Wall", WL + "_C", editable=True)
    en = V("Enemy")
    loc = lambda x, z: f"(Math|Vector|MakeVector {x} 0.0 {z})"
    move = lambda who, x, z: f"(Transformation|SetActorLocation :self {who} :NewLocation {loc(x, z)} :bSweep false :bTeleport true)"
    s = lambda e: f"(Utilities|String|ToString(Boolean) {e})"
    report = f"""
    (bind hc {HEALTH_CAST.format(V('Target'))}
      (:then (Development|PrintString (Utilities|String|Append "EN state="
        (Utilities|String|Append (Utilities|String|ToString(Integer) (Class|BPEnemy|GetState :self {en}))
        (Utilities|String|Append " see=" (Utilities|String|Append {s(f'(Class|BPEnemy|GetCanSeeTarget :self {en})')}
        (Utilities|String|Append " range=" (Utilities|String|Append {s(f'(Class|BPEnemy|GetInAttackRange :self {en})')}
        (Utilities|String|Append " dist=" (Utilities|String|Append (Utilities|String|ToString(Float) (Transformation|GetDistanceTo :self {en} :OtherActor {V('Target')}))
        (Utilities|String|Append " hp=" (Utilities|String|Append (Utilities|String|ToString(Float) (Class|BPHealthComponent|GetHealth :self hc))
        (Utilities|String|Append " anim=" (Utilities|GetDisplayName :Object (Class|BPEnemy|GetCurrentAnim :self {en})))))))))))))))
      (:CastFailed))"""

    def phase(tx, wall_x):
        return f"""
    {move(en, 0.0, STAND)}
    {move(V('Target'), tx, Z + 110.0)}
    {move(V('Wall'), wall_x, Z + 210.0)}
    (Class|BPEnemy|SetPatrolSign :self {en} :PatrolSign 1.0)
    (Class|BPEnemy|Think :self {en})""" + report

    far_wall = 5000.0
    code = '(event AddEvent|EventBeginPlay (Development|PrintString "EN_READY"))\n(event AddEvent|EventTick (DeltaSeconds)'
    code += key("One", phase(3000.0, far_wall)) + key("Two", phase(800.0, far_wall))
    code += key("Three", phase(150.0, far_wall)) + key("Four", phase(800.0, 400.0)) + key("R", report) + ")"
    must("BP", "write_graph_dsl", {"graph": T + ":EventGraph", "code": code})
    compile_bp(T)


def verify():
    place(LEVEL, AR, "EnemyArena", (0, 0, Z))
    enemy = place(LEVEL, E, "Enemy", (0, 0, STAND))
    target = place(LEVEL, TG, "EnemyTarget", (3000, 0, Z + 110))
    wall = place(LEVEL, WL, "EnemyWall", (5000, 0, Z + 210))
    test = place(LEVEL, T, "EnemyTest", (0, 0, Z + 500))
    set_props(test, {"Enemy": enemy["refPath"], "Target": target["refPath"], "Wall": wall["refPath"]}, "EnemyTest")
    set_props(enemy, {"Target": target["refPath"]}, "Enemy")
    try:
        with PIE() as p:
            time.sleep(3)
            ready = p.markers("ENEMY_READY")
            assert "ENEMY_READY" in ready, "enemy did not start"
            assert f"socket=true at={SOCKET}" in ready, f"weapon not on {SOCKET}: {ready[-200:]}"
            print(f"  weapon attached to {SOCKET}")

            def last():
                line = p.markers("EN state=").rsplit("EN state=", 1)[1].split('"')[0]
                st = dict(kv.split("=", 1) for kv in ("state=" + line).split())
                st["dist"], st["hp"] = float(st["dist"]), float(st["hp"])
                return st

            def press(k, first=False):
                if first:
                    p.press_expect(k, "EN state=")  # the first key after StartPIE can be dropped
                else:
                    n = p.markers("EN state=").count("EN state=")
                    p.key(k, focus_game=False)
                    assert p.markers("EN state=").count("EN state=") > n, f"{k}: no state print"
                return last()

            def expect(k, state, see, rng, anim, first=False):
                st = press(k, first)
                want = {"state": str(state), "see": see, "range": rng, "anim": anim}
                got = {x: st[x] for x in want}
                assert got == want, f"{k}: got {st}, wanted {want}"
                print(f"  {k}: {st}")
                return st

            st = expect("One", 0, "false", "false", "MM_Idle", first=True)
            time.sleep(2)
            moved = press("R")
            assert st["dist"] - moved["dist"] > 100, f"patrol did not move: {st['dist']} -> {moved['dist']}"
            print(f"  patrol: dist {st['dist']:.0f} -> {moved['dist']:.0f}")

            st = expect("Two", 1, "true", "false", "MF_Unarmed_Jog_Fwd")
            time.sleep(1.0)
            moved = press("R")
            # By the time R lands the enemy may already have closed in and switched to attacking.
            assert st["dist"] - moved["dist"] > 150 and moved["state"] in ("1", "2"), f"chase: {st} -> {moved}"
            print(f"  chase: dist {st['dist']:.0f} -> {moved['dist']:.0f}")

            st = expect("Three", 2, "true", "true", "MM_Attack_01")
            time.sleep(2.5)
            hit = press("R")
            assert st["hp"] - hit["hp"] >= 20, f"attack damage: hp {st['hp']} -> {hit['hp']}"
            print(f"  attack: hp {st['hp']:.0f} -> {hit['hp']:.0f}")

            expect("Four", 0, "false", "false", "MM_Idle")
    finally:
        for x in (T, E, TG, WL, AR):
            unplace(LEVEL, x)
        save([LEVEL])
    print("ENEMY PASS")


if __name__ == "__main__":
    mcp.init()
    if not must("Asset", "exists", {"path": H}):
        raise Fail("build the health recipe first: python3 recipes/health/build/health.py")
    if "--verify-only" not in sys.argv:
        if "--fresh" in sys.argv:
            wipe()
        build_props()
        build_enemy()
        build_test()
        save([x.split(".")[0] for x in (E, TG, WL, AR, T)])
    verify()
