"""Blueprint helpers shared by the gameplay recipes (magic, weapons, vehicles)."""
import json
from uikit import must, ref, Fail


def create(path, parent):
    folder, name = path.rsplit("/", 1)[0], path.rsplit(".", 1)[1]
    must("BP", "create", {"folder_path": folder, "asset_name": name, "asset_type": ref(parent)})


def var(bp, n, t, container=None):
    if n in (must("BP", "list_variables", {"blueprint": ref(bp), "graph": None}) or []):
        return
    must("BP", "add_variable", {"blueprint": ref(bp), "name": n, "type_name": t, "graph": None, "container_type": container})


def obj_var(bp, n, cls, container=None, editable=False):
    must("BP", "add_object_variable", {"blueprint": ref(bp), "name": n, "object_class": ref(cls),
                                       "graph": None, "container_type": container})
    if editable:
        must("BP", "set_variable_instance_editable", {"blueprint": ref(bp), "variable_name": n, "instance_editable": True})


def read_back(instance, values, label):
    got = json.loads(must("Object", "get_properties", {"instance": instance, "properties": list(values)}))
    for k, v in values.items():
        g = got.get(k)
        ok = abs(g - v) < 1e-3 if isinstance(v, (int, float)) and isinstance(g, (int, float)) else (
            v.split(".")[-1] in json.dumps(g) if isinstance(v, str) and v.startswith("/") else True)
        if not ok:
            raise Fail(f"{label}.{k} = {g}, wanted {v}")
    return got


def set_props(instance, values, label):
    must("Object", "set_properties", {"instance": instance, "values": json.dumps(values)})
    return read_back(instance, values, label)


def defaults(bp, values):
    """Variable defaults live on the class default object; there is no per-variable default tool."""
    must("BP", "compile_blueprint", {"blueprint": ref(bp)})
    set_props(must("BP", "get_default_object", {"blueprint": ref(bp)}), values, bp)


def fn(bp, name, params, outputs, code):
    """params/outputs: [(name, type)]; a type ending in _C is an object class path."""
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
        set_props(c, props, name)
    return c


def ensure_bp(path, parent):
    """Create the Blueprint unless it exists. Data definitions are kept across --fresh runs: deleting a
    class that data assets use leaves them loaded and blocks recreating them (see uikit.delete_assets)."""
    if not must("Asset", "exists", {"path": path}):
        create(path, parent)


def data_assets(folder, cls, assets):
    """Create missing data assets and (re)write every listed value."""
    for n, vals in assets.items():
        if not must("Asset", "exists", {"path": f"{folder}/{n}.{n}"}):
            must("DataAsset", "create", {"folder_path": folder, "asset_name": n, "asset_type": ref(cls)})
        set_props(ref(f"{folder}/{n}.{n}"), vals, n)


def key(k, body):
    """Poll a key on Tick; key events written as DSL events do not fire."""
    return f"""
  (if (Game|Player|WasInputKeyJustPressed :self (Game|GetPlayerController 0) :Key "{k}"){body})"""


def compile_bp(bp):
    must("BP", "compile_blueprint", {"blueprint": ref(bp)})


CHANNELS = ["WorldStatic", "WorldDynamic", "Pawn", "Visibility", "Camera", "PhysicsBody", "Vehicle", "Destructible"]
_PRESETS = {"BlockAll": ("QueryAndPhysics", "ECC_WorldStatic", "ECR_Block"),
            "OverlapAll": ("QueryOnly", "ECC_WorldDynamic", "ECR_Overlap"),
            "NoCollision": ("NoCollision", "ECC_WorldStatic", "ECR_Ignore")}


def collision(preset):
    """bodyInstance value for a component template. Setting collisionProfileName alone on a template
    renames the profile but keeps the old per-channel responses, so traces and overlaps ignore it."""
    enabled, obj, resp = _PRESETS[preset]
    return {"collisionProfileName": preset, "collisionEnabled": enabled, "objectType": obj,
            "collisionResponses": {"responseArray": [{"channel": c, "response": resp} for c in CHANNELS]}}
