#!/usr/bin/env python3
"""Builds and PIE-verifies the inventory recipe: item definitions, inventory component, pickup.

  python3 recipes/inventory/build/inventory.py [--fresh] [--verify-only]
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, ensure_level, Fail, PIE

F = "/Game/Inventory"
D = f"{F}/BP_ItemDefinition.BP_ItemDefinition"
I = f"{F}/BP_InventoryComponent.BP_InventoryComponent"
P = f"{F}/BP_Pickup.BP_Pickup"
T = f"{F}/BP_InventoryTest.BP_InventoryTest"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
ITEMS = {"DA_Potion": {"DisplayName": "Health Potion", "MaxStack": 5},
         "DA_Coin": {"DisplayName": "Gold Coin", "MaxStack": 99}}
V = lambda n: f"(Variables|Default|Get{n})"
FRESH = "--fresh" in sys.argv


def wipe():
    # Delete dependents first; deleting an asset that is still referenced fails without an error.
    ensure_level(LEVEL)
    unplace(LEVEL, T)
    unplace(LEVEL, P)
    save([LEVEL])
    for path in [T, P, I] + [f"{F}/Items/{n}.{n}" for n in ITEMS] + [D]:
        if must("Asset", "exists", {"path": path}):
            must("Asset", "delete", {"path": path})
            if must("Asset", "exists", {"path": path}):
                raise Fail(f"could not delete {path}")


def create(path, parent):
    folder, name = path.rsplit("/", 1)[0], path.rsplit(".", 1)[1]
    must("BP", "create", {"folder_path": folder, "asset_name": name, "asset_type": ref(parent)})


def var(bp, n, t, container=None):
    must("BP", "add_variable", {"blueprint": ref(bp), "name": n, "type_name": t, "graph": None, "container_type": container})


def fn(bp, name, params, outputs, code):
    """params/outputs: [(name, type)] where type is a basic type name or an object class path ending in _C."""
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


def build_items():
    for n in ITEMS:
        p = f"{F}/Items/{n}.{n}"
    create(D, "/Script/Engine.PrimaryDataAsset")
    var(D, "DisplayName", "string")
    var(D, "MaxStack", "int")
    must("BP", "compile_blueprint", {"blueprint": ref(D)})
    for n, vals in ITEMS.items():
        if not must("Asset", "exists", {"path": f"{F}/Items/{n}.{n}"}):
            must("DataAsset", "create", {"folder_path": F + "/Items", "asset_name": n, "asset_type": ref(D + "_C")})
        inst = ref(f"{F}/Items/{n}.{n}")
        import json
        must("Object", "set_properties", {"instance": inst, "values": json.dumps(vals)})
        got = json.loads(must("Object", "get_properties", {"instance": inst, "properties": list(vals)}))
        assert got == vals, f"{n}: {got}"


def build_inventory():
    create(I, "/Script/Engine.ActorComponent")
    must("BP", "add_object_variable", {"blueprint": ref(I), "name": "Items", "object_class": ref(D + "_C"),
                                       "graph": None, "container_type": "ARRAY"})
    var(I, "Counts", "int", "ARRAY")
    var(I, "LastAdded", "int")
    must("BP", "add_event_dispatcher", {"blueprint": ref(I), "name": "OnInventoryChanged"})
    item = D + "_C"
    # FindItem and Get are pure: they re-run on every read, so a value needed after a write is
    # stored in a member variable (LastAdded) before the write.
    fn(I, "AddItem", [("Item", item), ("Count", "int")], [("Added", "int")], f"""(fn AddItem (Item Count)
  (if (< (Utilities|Array|FindItem {V('Items')} Item) 0)
    (Utilities|Array|Add {V('Items')} Item)
    (Utilities|Array|Add {V('Counts')} 0))
  (bind i (Utilities|Array|FindItem {V('Items')} Item))
  (bind cur (Utilities|Array|Get(acopy) {V('Counts')} i))
  (bind room (- (Class|BPItemDefinition|GetMaxStack :self Item) cur))
  (Variables|Default|SetLastAdded (Math|Integer|Min(Integer) Count room))
  (Utilities|Array|SetArrayElem {V('Counts')} i (+ cur {V('LastAdded')}))
  (if (> {V('LastAdded')} 0)
    (Default|CallOnInventoryChanged))
  (return {V('LastAdded')}))""")
    fn(I, "GetCount", [("Item", item)], [("Count", "int")], f"""(fn GetCount (Item)
  (bind i (Utilities|Array|FindItem {V('Items')} Item))
  (if (< i 0)
    (return 0)
    (else
      (return (Utilities|Array|Get(acopy) {V('Counts')} i)))))""")
    fn(I, "RemoveItem", [("Item", item), ("Count", "int")], [("Removed", "bool")], f"""(fn RemoveItem (Item Count)
  (bind i (Utilities|Array|FindItem {V('Items')} Item))
  (if (< i 0)
    (return false)
    (else
      (bind cur (Utilities|Array|Get(acopy) {V('Counts')} i))
      (if (< cur Count)
        (return false)
        (else
          (Utilities|Array|SetArrayElem {V('Counts')} i (- cur Count))
          (Default|CallOnInventoryChanged)
          (return true))))))""")
    must("BP", "compile_blueprint", {"blueprint": ref(I)})


INV_CLS = f'"{I}_C"'


def with_inventory(actor, body):
    """Run body with `inv` bound to actor's BP_InventoryComponent; the cast is an exec node."""
    return f"""
  (bind inv (Utilities|Casting|CastToBP_InventoryComponent
      :Object (Actor|GetComponentbyClass :self {actor} :ComponentClass {INV_CLS}))
    (:then{body})
    (:CastFailed))"""


def key(k, body):
    return f"""
  (if (Game|Player|WasInputKeyJustPressed :self (Game|GetPlayerController 0) :Key "{k}"){body})"""


def build_pickup():
    create(P, "/Script/Engine.Actor")
    must("Actor", "add_component", {"owner": ref(P), "component_type": ref("/Script/Engine.SphereComponent"), "name": "Trigger"})
    vis = must("Actor", "add_component", {"owner": ref(P), "component_type": ref("/Script/Engine.StaticMeshComponent"),
                                          "name": "Visual"})
    # PrimitiveTools.add_sphere only accepts level actors; on a Blueprint, set the template's mesh.
    vals = {"staticMesh": "/Engine/BasicShapes/Sphere.Sphere", "relativeScale3D": {"x": 0.4, "y": 0.4, "z": 0.4},
            "bodyInstance": {"collisionProfileName": "NoCollision"}}
    import json
    must("Object", "set_properties", {"instance": vis, "values": json.dumps(vals)})
    got = must("Object", "get_properties", {"instance": vis, "properties": list(vals)})
    assert "Sphere" in got and "NoCollision" in got, got
    must("BP", "add_object_variable", {"blueprint": ref(P), "name": "Item", "object_class": ref(D + "_C"),
                                       "graph": None, "container_type": None})
    var(P, "Count", "int")
    for n in ("Item", "Count"):
        must("BP", "set_variable_instance_editable", {"blueprint": ref(P), "variable_name": n, "instance_editable": True})
    body = f"""
      (if (> (Class|BPInventoryComponent|AddItem :self inv :Item {V('Item')} :Count {V('Count')}) 0)
        (Development|PrintString "INV_PICKED")
        (Actor|DestroyActor :self self))"""
    must("BP", "write_graph_dsl", {"graph": P + ":EventGraph",
         "code": "(event AddEvent|EventBeginPlay (Development|PrintString (Utilities|String|Append \"INV_AT \" (Utilities|String|ToString(Vector) (Transformation|GetActorLocation :self self)))))\n(event AddEvent|Collision|EventActorBeginOverlap (OtherActor) (Development|PrintString \"INV_OVERLAP\")" + with_inventory("OtherActor", body) + ")"})
    must("BP", "compile_blueprint", {"blueprint": ref(P)})


def build_test():
    """T: give the pawn an inventory and move it onto the pickup. A: add 10 potions (stack 5).
    X: remove 1 coin. R: print counts."""
    create(T, "/Script/Engine.Actor")
    pawn = "(Game|GetPlayerPawn 0)"
    potion, coin = f'"{F}/Items/DA_Potion.DA_Potion"', f'"{F}/Items/DA_Coin.DA_Coin"'
    count = lambda item: f"(Utilities|String|ToString(Integer) (Class|BPInventoryComponent|GetCount :self inv :Item {item}))"
    give = f"""
    (Game|AddComponentbyClass :self {pawn} :Class {INV_CLS})
    (Transformation|SetActorLocation :self {pawn} :NewLocation (Math|Vector|MakeVector 500.0 0.0 0.0) :bSweep false :bTeleport true)
    (Development|PrintString (Utilities|String|Append "INV_PAWN " (Utilities|GetDisplayName :Object {pawn})))"""
    report = f""" (Development|PrintString (Utilities|String|Append "INV potion="
        (Utilities|String|Append {count(potion)} (Utilities|String|Append " coin=" {count(coin)}))))"""
    code = '(event AddEvent|EventBeginPlay (Development|PrintString "INV_READY"))\n(event AddEvent|EventTick (DeltaSeconds)'
    code += key("T", give)
    code += key("A", with_inventory(pawn, f" (Class|BPInventoryComponent|AddItem :self inv :Item {potion} :Count 10)"))
    code += key("X", with_inventory(pawn, f" (Class|BPInventoryComponent|RemoveItem :self inv :Item {coin} :Count 1)"))
    code += key("R", with_inventory(pawn, report)) + ")"
    must("BP", "write_graph_dsl", {"graph": T + ":EventGraph", "code": code})
    must("BP", "compile_blueprint", {"blueprint": ref(T)})


def place_pickup():
    import json
    place(LEVEL, P, "Pickup_Coin")
    actors = must("Scene", "find_actors", {"root": None, "name": "", "actor_type": ref(P + "_C"), "tag": "",
                                           "bounds": None, "collision_channels": []})
    a = actors[0] if isinstance(actors[0], dict) else ref(actors[0])
    # Actor.set_actor_transform returns success but leaves the actor at the origin; move the root component instead.
    # Z writes on this placed actor read back as 0, so the test keeps everything at Z=0.
    root = json.loads(must("Object", "get_properties", {"instance": a, "properties": ["RootComponent"]}))["RootComponent"]
    must("Object", "set_properties", {"instance": root, "values": json.dumps({"relativeLocation": {"x": 500, "y": 0, "z": 0}})})
    assert '"x":500' in must("Object", "get_properties", {"instance": root, "properties": ["relativeLocation"]}).replace(".0", "")
    must("Object", "set_properties", {"instance": a, "values": json.dumps({"Item": f"{F}/Items/DA_Coin.DA_Coin", "Count": 3})})
    got = must("Object", "get_properties", {"instance": a, "properties": ["Item", "Count"]})
    assert "DA_Coin" in got and '"Count":3' in got, got


def verify():
    place(LEVEL, T, "InventoryTest")
    place_pickup()
    try:
        with PIE() as p:
            time.sleep(2)
            assert "INV_READY" in p.markers("INV_READY"), "test actor did not start"

            def state(k, first=False):
                p.key(k, focus_game=first)
                n = p.markers("INV potion=").count("INV potion=")
                p.key("R", focus_game=False)
                got = p.markers("INV potion=")
                assert got.count("INV potion=") > n, f"after {k}: no state print"
                return "potion=" + got.rsplit("INV potion=", 1)[1].split('"')[0]

            s = state("T", True)
            assert "INV_PICKED" in p.markers("INV_PICKED"), f"pickup overlap did not fire ({s}) overlap={p.markers('INV_OVERLAP').count('INV_OVERLAP')} {p.markers('INV_PAWN')[-80:]} {p.markers('INV_AT')[-120:]}"
            assert s == "potion=0 coin=3", f"after pickup: {s}"
            print("  pickup:", s)
            s = state("A")
            assert s == "potion=5 coin=3", f"after add 10 potions (stack 5): {s}"
            print("  add:", s)
            s = state("X")
            assert s == "potion=5 coin=2", f"after remove coin: {s}"
            print("  remove:", s)
    finally:
        unplace(LEVEL, T)
        unplace(LEVEL, P)
        save([LEVEL])
    print("INVENTORY PASS")


if __name__ == "__main__":
    mcp.init()
    if "--verify-only" not in sys.argv:
        if FRESH:
            wipe()
        build_items()
        build_inventory()
        build_pickup()
        build_test()
        save([x.split(".")[0] for x in (D, I, P, T)] + [f"{F}/Items/{n}" for n in ITEMS])
    verify()
