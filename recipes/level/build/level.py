#!/usr/bin/env python3
"""Generates a blockout level from an ASCII layout: floor tiles, walls, a player start, enemy spawn
markers, a seeded prop scatter and a lighting mood. Verifies the geometry with downward traces in the
editor and with a Third Person character standing on the generated floor in PIE.

  python3 recipes/level/build/level.py [--mood day|dusk|night] [--seed N] [--verify-only]

Every run regenerates the level from scratch, so there is no --fresh.
"""
import os, sys, time, json, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, PIE, Fail
from bpkit import create, key, compile_bp, set_props

F = "/Game/Generated"
LEVEL = f"{F}/L_Generated"
LP = f"{LEVEL}.L_Generated:PersistentLevel."
TEMPLATE = "/Engine/Maps/Templates/Template_Default"
PROBE = f"{F}/BP_LevelProbe.BP_LevelProbe"
# /Game/ThirdPerson/Blueprints came from the C++ template and has no parent class in this Blueprint-only
# project; the Guard pack ships working Blueprint copies.
GAME_MODE = "/Game/Guard/Demo/ThirdPerson/Blueprints/BP_ThirdPersonGameMode.BP_ThirdPersonGameMode_C"
CUBE, CYL = "/Engine/BasicShapes/Cube.Cube", "/Engine/BasicShapes/Cylinder.Cylinder"
FOLDER = "Generated"
TILE, WALL_H, FLOOR_T = 400.0, 300.0, 20.0

# '#' wall, '.' floor, 'S' player start, 'E' enemy spawn marker. Row 0 is +X, column 0 is -Y.
LAYOUT = """
##########
#S...#...#
#....#.E.#
#........#
#....#...#
###.####.#
#........#
#.E....E.#
##########
"""
PROPS = {"crate": (CUBE, (0.8, 0.8, 0.8)), "pillar": (CYL, (0.6, 0.6, 1.6))}
PROP_COUNT = 8
MOODS = {
    "day": {"pitch": -50.0, "sun": 8.0, "color": (1.0, 0.96, 0.9), "sky": 1.0, "fog": 0.02},
    "dusk": {"pitch": -8.0, "sun": 4.0, "color": (1.0, 0.55, 0.3), "sky": 0.6, "fog": 0.06},
    "night": {"pitch": -40.0, "sun": 0.3, "color": (0.5, 0.6, 1.0), "sky": 0.15, "fog": 0.03},
}


def capsule_half():
    """Half height of the game mode's pawn capsule (BP_Guard: 88)."""
    gm, cls = GAME_MODE.rsplit(".", 1)
    pawn = json.loads(must("Object", "get_properties", {"instance": ref(f"{gm}.Default__{cls}"), "properties": ["defaultPawnClass"]}))
    pp, pc = pawn["defaultPawnClass"]["refPath"].rsplit(".", 1)
    cap = json.loads(must("Object", "get_properties", {"instance": ref(f"{pp}.Default__{pc}"), "properties": ["CapsuleComponent"]}))
    return json.loads(must("Object", "get_properties", {"instance": cap["CapsuleComponent"], "properties": ["capsuleHalfHeight"]}))["capsuleHalfHeight"]


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def grid():
    rows = LAYOUT.strip("\n").splitlines()
    w = max(len(r) for r in rows)
    return [r.ljust(w, "#") for r in rows]


def cell_xy(r, c, rows):
    return ((len(rows) - 1) / 2 - r) * TILE, (c - (len(rows[0]) - 1) / 2) * TILE


def plan(seed):
    """Pure function of the layout and seed: every mesh to place, as (label, asset, x, y, z, yaw, scale)."""
    rows = grid()
    out, floors, keep_clear = [], [], set()
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            x, y = cell_xy(r, c, rows)
            if ch == "#":
                out.append((f"Wall_{r}_{c}", CUBE, x, y, WALL_H / 2, 0.0, (TILE / 100, TILE / 100, WALL_H / 100)))
                continue
            out.append((f"Floor_{r}_{c}", CUBE, x, y, -FLOOR_T / 2, 0.0, (TILE / 100, TILE / 100, FLOOR_T / 100)))
            if ch in "SE":
                keep_clear |= {(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)}
            else:
                floors.append((r, c))
    # A doorway is a floor cell with walls on two opposite sides; a prop there would block the path.
    door = lambda r, c: (rows[r - 1][c] == "#" and rows[r + 1][c] == "#") or (rows[r][c - 1] == "#" and rows[r][c + 1] == "#")
    spots = [rc for rc in floors if rc not in keep_clear and not door(*rc)]
    rng = random.Random(seed)
    for i, (r, c) in enumerate(sorted(rng.sample(spots, min(PROP_COUNT, len(spots))))):
        kind = rng.choice(sorted(PROPS))
        asset, scale = PROPS[kind]
        x, y = cell_xy(r, c, rows)
        x += rng.uniform(-80, 80)
        y += rng.uniform(-80, 80)
        out.append((f"Prop_{kind}_{i}", asset, round(x, 1), round(y, 1), scale[2] * 50, round(rng.uniform(0, 360), 1), scale))
    return out


def markers():
    rows = grid()
    return [(ch, *cell_xy(r, c, rows)) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch in "SE"]


def xf(x, y, z, yaw=0.0, scale=(1, 1, 1)):
    return {"location": {"x": x, "y": y, "z": z}, "rotation": {"pitch": 0, "yaw": yaw, "roll": 0},
            "scale": {"x": scale[0], "y": scale[1], "z": scale[2]}}


def open_level():
    if not must("Asset", "exists", {"path": LEVEL}):
        must("Asset", "duplicate", {"path": TEMPLATE, "new_path": LEVEL})
        save([LEVEL])
    if LEVEL not in str(must("Scene", "get_current_level", {})):
        must("Scene", "load_level", {"level_path": LEVEL})


def generated():
    if FOLDER not in str(must("Scene", "get_folders", {})):
        return []
    return [a if isinstance(a, dict) else ref(a)
            for a in must("Scene", "get_actors_in_folder", {"folder_path": FOLDER, "recursive": True}) or []]


def clear():
    for a in generated():
        must("Scene", "remove_from_scene", {"actor": a})
    if must("Scene", "find_actors", {"root": None, "name": "Floor_0", "actor_type": None, "tag": "",
                                     "bounds": None, "collision_channels": []}):
        # The template's floor sits at Z=0 under everything; the generated tiles replace it.
        must("Scene", "remove_from_scene", {"actor": ref(LP + "Floor_0")})


def generate(seed, mood):
    open_level()
    clear()
    for label, asset, x, y, z, yaw, scale in plan(seed):
        a = must("Scene", "add_to_scene_from_asset", {"asset_path": asset, "name": label, "xform": xf(x, y, z, yaw, scale),
                                                      "parent": None, "snap_to_ground": False})
        must("Scene", "set_actor_folder", {"actor": a, "folder_path": f"{FOLDER}/{label.split('_')[0]}"})
    for i, (ch, x, y) in enumerate(markers()):
        if ch == "S":
            must("Actor", "set_actor_transform", {"actor": ref(LP + "PlayerStart_0"), "xform": xf(x, y, capsule_half() + 2), "worldspace": True})
        else:
            a = must("Scene", "add_to_scene_from_class", {"actor_type": ref("/Script/Engine.TargetPoint"), "name": f"EnemySpawn_{i}",
                                                           "xform": xf(x, y, 0.0), "parent": None, "snap_to_ground": False})
            must("Actor", "add_tag", {"actor": a, "tag": "EnemySpawn"})
            must("Scene", "set_actor_folder", {"actor": a, "folder_path": f"{FOLDER}/Spawns"})
    m = MOODS[mood]
    # Write the whole rotation with roll 0. The template sun has roll 112; changing only its pitch through
    # set_actor_transform read back as the new pitch but rendered the sun near the horizon (orange, long shadows).
    must("Actor", "set_actor_transform", {"actor": ref(LP + "DirectionalLight_0"), "worldspace": True, "xform": {
        "location": {"x": 0, "y": 0, "z": 400}, "rotation": {"pitch": m["pitch"], "yaw": -30.0, "roll": 0.0},
        "scale": {"x": 1, "y": 1, "z": 1}}})
    r, g, b = m["color"]
    set_props(ref(LP + "DirectionalLight_0.LightComponent0"), {"intensity": m["sun"], "lightColor": {"r": r, "g": g, "b": b, "a": 1.0}}, "Sun")
    set_props(ref(LP + "SkyLight_0.SkyLightComponent0"), {"intensity": m["sky"]}, "SkyLight")
    set_props(ref(LP + "ExponentialHeightFog_0.HeightFogComponent0"), {"fogDensity": m["fog"]}, "Fog")
    # The class property only accepts a loaded class.
    must("Asset", "load_asset", {"asset_path": GAME_MODE.rsplit(".", 1)[0] + "." + GAME_MODE.rsplit(".", 1)[1][:-2]})
    set_props(ref(LP + "WorldSettings_1"), {"defaultGameMode": GAME_MODE}, "WorldSettings")
    save([LEVEL])


def build_probe():
    if must("Asset", "exists", {"path": PROBE}):
        return
    create(PROBE, "/Script/Engine.Actor")
    report = '\n    (Development|PrintString (Utilities|String|Append "LVL pawn=" (Utilities|String|ToString(Vector) (Transformation|GetActorLocation :self (Game|GetPlayerPawn 0)))))'
    must("BP", "write_graph_dsl", {"graph": PROBE + ":EventGraph", "code":
         '(event AddEvent|EventBeginPlay (Development|PrintString "LVL_READY"))\n(event AddEvent|EventTick (DeltaSeconds)' + key("R", report) + ")"})
    compile_bp(PROBE)
    save([PROBE.split(".")[0]])


def verify_geometry(seed):
    expected = plan(seed)
    labels = [must("Actor", "get_label", {"actor": a}) for a in generated()]
    want = [e[0] for e in expected] + [f"EnemySpawn_{i}" for i, (ch, _, _) in enumerate(markers()) if ch == "E"]
    if sorted(labels) != sorted(want):
        raise Fail(f"actors: {len(labels)} placed, {len(want)} planned; missing {sorted(set(want) - set(labels))[:5]}")
    # Trace straight down through every wall, prop and bare floor tile: the first hit must be the planned top.
    probes = [(x, y, z + s[2] * 50) for label, a, x, y, z, yaw, s in expected if not label.startswith("Floor")]
    # A prop is offset up to 80 units inside its tile, so it can cover the tile centre; skip those tiles.
    props = [(x, y) for label, a, x, y, z, yaw, s in expected if label.startswith("Prop")]
    probes += [(x, y, 0.0) for label, a, x, y, z, yaw, s in expected if label.startswith("Floor")
               and all(abs(x - px) >= TILE / 2 or abs(y - py) >= TILE / 2 for px, py in props)]
    top = 2000.0
    for x, y, want_z in probes:
        d = must("Scene", "trace_world", {"start": {"x": x, "y": y, "z": top}, "end": {"x": x, "y": y, "z": -500.0}})
        d = d.get("distance", d) if isinstance(d, dict) else d
        if d is None or abs((top - float(d)) - want_z) > 1.0:
            raise Fail(f"trace at ({x}, {y}): hit z={None if d is None else top - float(d)}, wanted {want_z}")
    n = {k: sum(e[0].startswith(k) for e in expected) for k in ("Wall", "Floor", "Prop")}
    print(f"  {n['Floor']} floor tiles, {n['Wall']} walls, {n['Prop']} props; {len(probes)} downward traces hit the planned tops")


def verify_play():
    sx, sy = next((x, y) for ch, x, y in markers() if ch == "S")
    probe = place(LEVEL, PROBE, "LevelProbe", (0, 0, 1000))
    try:
        with PIE() as p:
            time.sleep(3)
            assert "LVL_READY" in p.markers("LVL_READY"), "probe did not start"

            def pawn():
                v = p.markers("LVL pawn=").rsplit("LVL pawn=", 1)[1].split('"')[0]
                return [float(kv.split("=")[1]) for kv in v.split()]

            p.press_expect("R", "LVL pawn=")  # the first key after StartPIE can be dropped
            first = pawn()
            time.sleep(2)
            p.press_expect("R", "LVL pawn=")
            x, y, z = pawn()
            assert abs(x - sx) < 50 and abs(y - sy) < 50, f"pawn at ({x}, {y}), start cell at ({sx}, {sy})"
            # CharacterMovement keeps the capsule 1.9 to 2.4 units above the floor it stands on (top at Z=0).
            half = capsule_half()
            assert half + 1.9 <= z <= half + 2.4 and abs(z - first[2]) < 0.1, f"pawn z {first[2]} -> {z}, capsule half {half}"
            print(f"  character stands on the start tile at ({x:.0f}, {y:.0f}, {z:.1f})")
            p.capture(os.path.join(os.environ.get("UI_OUT", "/tmp"), "L_Generated.png"))
    finally:
        unplace(LEVEL, PROBE)
        save([LEVEL])


if __name__ == "__main__":
    mcp.init()
    seed, mood = int(arg("--seed", 7)), arg("--mood", "dusk")
    if mood not in MOODS:
        raise Fail(f"--mood must be one of {sorted(MOODS)}")
    if "--verify-only" not in sys.argv:
        build_probe()
        generate(seed, mood)
    else:
        open_level()
    verify_geometry(seed)
    verify_play()
    print("LEVEL PASS")
