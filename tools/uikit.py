"""Data-driven UMG builder on Epic's Unreal MCP. Every write is read back."""
import base64, json, os, time
import mcp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Fail(Exception):
    pass


def must(toolset, tool, args):
    ok, out = mcp.call(toolset, tool, args)
    if not ok:
        raise Fail(f"{tool} {json.dumps(args)[:300]} -> {out}")
    return out.get("returnValue") if isinstance(out, dict) else out


def ref(p):
    return {"refPath": p}


class Theme:
    def __init__(self, path=os.path.join(ROOT, "recipes/ui/theme.example.json")):
        self.t = json.load(open(path))

    def color(self, name, alpha=None):
        c = dict(self.t["colors"][name])
        if alpha is not None:
            c["a"] = alpha
        return {"specifiedColor": c, "colorUseRule": "UseColor_Specified"}

    def font(self, role):
        face = self.t["font"]["typefaces"]["title" if role == "title" else "body"]
        return {"fontObject": self.t["font"]["asset"], "typefaceFontName": face, "size": self.t["sizes"][role]}

    def brush(self, name, alpha=None, radius=None):
        r = self.t["radius"] if radius is None else radius
        return {"drawAs": "RoundedBox", "tintColor": self.color(name, alpha),
                "outlineSettings": {"cornerRadii": {"x": r, "y": r, "z": r, "w": r},
                                    "roundingType": "FixedRadius", "width": 0}}

    def pad(self, key):
        v = self.t["spacing"][key]
        return {"left": v, "top": v, "right": v, "bottom": v}


def _sub(want, got):
    """True when every field in want matches got (floats within 1e-3)."""
    if isinstance(got, dict) and set(got) == {"refPath"}:
        got = got["refPath"]
    if isinstance(want, dict):
        return isinstance(got, dict) and all(_sub(v, got.get(k)) for k, v in want.items())
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(want - got) < 1e-3
    if isinstance(want, str) and isinstance(got, str):
        return want.split(".")[-1].lower() == got.split(".")[-1].lower() or want in got
    return want == got


class WidgetBP:
    def __init__(self, folder, name):
        self.name = name
        self.path = f"{folder}/{name}.{name}"
        self.folder = folder
        self.slots = {}

    def w(self, name):
        return f"{self.path}:WidgetTree.{name}"

    def create(self):
        if must("Asset", "exists", {"path": self.path}):
            raise Fail(f"{self.path} exists; delete it or pick another name")
        must("UMG", "CreateWidgetBlueprint", {"folderPath": self.folder, "assetName": self.name,
                                              "parentClass": ref("/Script/UMG.UserWidget")})

    def add(self, cls, name, parent=None, variable=False):
        a = {"widgetBlueprint": ref(self.path), "widgetClass": ref("/Script/UMG." + cls), "widgetDisplayName": name}
        if parent:
            a["parentWidget"] = ref(self.w(parent))
        out = must("UMG", "AddWidget", a)
        if out["slot"] != "None":
            self.slots[name] = out["slot"]["refPath"]
        if variable and not out["bIsVariable"]:
            must("UMG", "ToggleWidgetAsVariable", {"widgetBlueprint": ref(self.path), "widget": ref(self.w(name)), "bIsVariable": True})

    def set(self, target, values):
        """target: widget name, or 'slot:<name>'. Writes then reads back every key."""
        path = self.slots[target[5:]] if target.startswith("slot:") else self.w(target)
        must("Object", "set_properties", {"instance": ref(path), "values": json.dumps(values)})
        got = must("Object", "get_properties", {"instance": ref(path), "properties": list(values)})
        got = json.loads(got) if isinstance(got, str) else got
        for k, v in values.items():
            if not _sub(v, got.get(k)):
                raise Fail(f"read-back mismatch {target}.{k}: want {v} got {got.get(k)}")

    def graph(self, code, graph="EventGraph"):
        must("BP", "write_graph_dsl", {"graph": f"{self.path}:{graph}", "code": code})

    def bind_click(self, button):
        must("UMG", "BindToEventProperty", {"widgetBlueprint": ref(self.path), "eventName": "OnClicked",
                                            "propertyName": button, "propertyClass": ref("/Script/UMG.Button")})

    def function(self, name, body):
        """body: DSL statements. Creates the graph first; write_graph_dsl cannot create function graphs."""
        must("BP", "add_function_graph", {"blueprint": ref(self.path), "graph_name": name})
        self.graph(f"(fn {name} ()\n{body})", graph=name)

    def var(self, name, type_name):
        must("BP", "add_variable", {"blueprint": ref(self.path), "name": name, "type_name": type_name,
                                     "graph": None, "container_type": None})

    def compile(self):
        if not must("UMG", "CompileWidgetBlueprint", {"widgetBlueprint": ref(self.path)}):
            raise Fail(f"compile failed: {self.name}")


def canvas_fill():
    return {"layoutData": {"offsets": {"left": 0, "top": 0, "right": 0, "bottom": 0},
                           "anchors": {"minimum": {"x": 0, "y": 0}, "maximum": {"x": 1, "y": 1}},
                           "alignment": {"x": 0, "y": 0}}}


def canvas_at(ax, ay, x=0, y=0, w=0, h=0, auto=True):
    d = {"layoutData": {"offsets": {"left": x, "top": y, "right": w, "bottom": h},
                        "anchors": {"minimum": {"x": ax, "y": ay}, "maximum": {"x": ax, "y": ay}},
                        "alignment": {"x": ax, "y": ay}}}
    if auto:
        d["bAutoSize"] = True
    return d


def style_text(bp, th, name, text, role, color="text"):
    bp.set(name, {"text": text, "font": th.font(role), "colorAndOpacity": th.color(color)})


def style_button(bp, th, name, normal):
    b = th.t["button"]
    bp.set(name, {"widgetStyle": {"normal": th.brush(normal), "hovered": th.brush(b["hovered"]),
                                  "pressed": th.brush(b["pressed"]),
                                  "normalPadding": {"left": 24, "top": 10, "right": 24, "bottom": 10}}})


def tween_fade_dsl(wbp, target, seconds, focus=None, tick_extra=""):
    """Opacity 0->1 with ease-out. Needs a `TweenElapsed` real variable and target exposed as variable."""
    focus_line = f"\n  (Widget|SetKeyboardFocus :self (Variables|{wbp}|Get{focus}))" if focus else ""
    return f"""
(event UserInterface|EventConstruct
  (Variables|Default|SetTweenElapsed 0.0)
  (Widget|SetRenderOpacity :self (Variables|{wbp}|Get{target}) :InOpacity 0.0){focus_line})
(event UserInterface|EventTick (MyGeometry InDeltaTime)
  (bind t (+ (Variables|Default|GetTweenElapsed) (Math|Float|Min(Float) InDeltaTime 0.0333)))
  (Variables|Default|SetTweenElapsed t)
  (bind a (Math|Float|Clamp(Float) (/ t {seconds}) 0.0 1.0))
  (bind inv (- 1.0 a))
  (Widget|SetRenderOpacity :self (Variables|{wbp}|Get{target}) :InOpacity (- 1.0 (* inv inv))){tick_extra})
"""


def save(paths):
    must("Asset", "save_assets", {"asset_paths": paths})


PLAYMODE = "PlayMode_InViewPort"


class PIE:
    """Play-in-Editor driver: start, press keys, click buttons by label, read markers."""

    def __enter__(self):
        if must("App", "IsPIERunning", {}):
            must("App", "StopPIE", {})
        self.seen = set(self._all())
        must("App", "StartPIE", {"options": {"bSimulate": False, "playMode": PLAYMODE, "warmupSeconds": 2}})
        self.t0 = time.time()
        return self

    def __exit__(self, *a):
        # Live Slate observers keep references to the game viewport; StopPIE then asserts
        # GameViewport.IsUnique() and crashes the editor.
        mcp.call("Slate", "Unobserve", {"ref": ""})
        if must("App", "IsPIERunning", {}):
            must("App", "StopPIE", {})

    def focus_game(self):
        """PressKey goes to the focused Slate widget; click the innermost large panel (the PIE viewport) first."""
        import re
        best = None
        for line in self.snapshot().splitlines():
            m = re.search(r"size=(\d+),(\d+).*\[ref=(\w+)\]", line)
            if m and int(m[1]) > 700 and int(m[2]) > 400 and not line.strip().startswith("window"):
                best = m[3]
        must("Slate", "Click", {"ref": best, "button": "left", "doubleClick": False})
        time.sleep(0.5)

    def key(self, k, focus_game=True):
        if focus_game:
            self.focus_game()
        must("Slate", "PressKey", {"key": k})
        time.sleep(1)

    def snapshot(self):
        must("Slate", "Observe", {"ref": "", "maxDepth": 60})
        try:
            return str(must("Slate", "Snapshot", {"ref": "", "maxDepth": 60, "bIncludeSourceLocations": False}))
        finally:
            mcp.call("Slate", "Unobserve", {"ref": ""})

    def button_ref(self, label):
        """Last match wins: the editor toolbar comes first in the snapshot and shows its own
        "Resume" button while the game is paused."""
        found = None
        for line in self.snapshot().splitlines():
            if line.strip().startswith("button") and f'"{label}"' in line and "[ref=" in line:
                found = line.split("[ref=")[1].split("]")[0]
        return found

    def click(self, label):
        r = self.button_ref(label)
        if not r:
            raise Fail(f"button '{label}' not on screen")
        must("Slate", "Hover", {"ref": r})
        must("Slate", "Click", {"ref": r, "button": "left", "doubleClick": False})
        time.sleep(1)

    def capture(self, out_png):
        d = must("App", "CaptureEditorImage", {})
        open(out_png, "wb").write(base64.b64decode(d["data"]))

    def _all(self, pattern=""):
        e = must("Logs", "GetLogEntries", {"category": "LogBlueprintUserMessages", "pattern": pattern, "maxEntries": 500})
        return e if isinstance(e, list) else (e or {}).get("entries", [])

    def markers(self, pattern):
        """Only entries logged after this PIE session started."""
        return json.dumps([x for x in self._all(pattern) if x not in self.seen])

    def running(self):
        return must("App", "IsPIERunning", {})


def build_menu(th, folder, spec):
    """Centered modal menu that scales with the project DPI curve (1080p reference units).

    SafeZone > CanvasPanel > Dim (fill) + Card (center anchor, auto size) > SizeBox (fixed width)
    > VerticalBox Panel > Title, [Subtitle], one SizeBox+Button+Label per button.
    spec: name, title, subtitle?, width, dim_alpha, buttons=[{id, label, style, body}],
    accept_key? (runs the first button), dismiss_key? (runs `dismiss` function name), on_open?
    Each button body becomes function Do<id>; OnClicked(<id>) calls it.
    """
    bp = WidgetBP(folder, spec["name"])
    bp.create()
    bp.add("SafeZone", "Safe")
    bp.add("CanvasPanel", "Root", "Safe")
    bp.add("Border", "Dim", "Root")
    bp.add("Border", "Card", "Root")
    bp.add("SizeBox", "CardWidth", "Card")
    bp.add("VerticalBox", "Panel", "CardWidth", variable=True)
    bp.add("TextBlock", "Title", "Panel")
    if spec.get("subtitle"):
        bp.add("TextBlock", "Subtitle", "Panel")
    for b in spec["buttons"]:
        bp.add("SizeBox", b["id"] + "Box", "Panel")
        bp.add("Button", b["id"], b["id"] + "Box", variable=True)
        bp.add("TextBlock", b["id"] + "Label", b["id"])

    sp = th.t["spacing"]
    bp.set("slot:Dim", canvas_fill())
    bp.set("Dim", {"background": th.brush("background", alpha=spec.get("dim_alpha", 0.6), radius=0)})
    bp.set("slot:Card", canvas_at(0.5, 0.5))
    bp.set("Card", {"background": th.brush("surface"), "padding": th.pad("outer")})
    bp.set("CardWidth", {"bOverride_WidthOverride": True, "widthOverride": spec.get("width", 420)})
    bp.set("Title", {"text": spec["title"], "font": th.font("title"), "colorAndOpacity": th.color("text"),
                     "justification": "Center"})
    bp.set("slot:Title", {"padding": {"left": 0, "top": 0, "right": 0, "bottom": sp["inner"]},
                          "horizontalAlignment": "HAlign_Fill"})
    if spec.get("subtitle"):
        bp.set("Subtitle", {"text": spec["subtitle"], "font": th.font("body"),
                            "colorAndOpacity": th.color("text_muted"), "justification": "Center"})
        bp.set("slot:Subtitle", {"padding": {"left": 0, "top": 0, "right": 0, "bottom": sp["inner"]},
                                 "horizontalAlignment": "HAlign_Fill"})
    for b in spec["buttons"]:
        i = b["id"]
        bp.set(i + "Box", {"bOverride_HeightOverride": True, "heightOverride": 56})
        bp.set("slot:" + i + "Box", {"padding": {"left": 0, "top": sp["gap"] / 2, "right": 0, "bottom": sp["gap"] / 2},
                                     "horizontalAlignment": "HAlign_Fill"})
        style_button(bp, th, i, b.get("style", "surface"))
        bp.set(i + "Label", {"text": b["label"], "font": th.font("body"), "colorAndOpacity": th.color("text"),
                             "justification": "Center"})
        bp.set("slot:" + i + "Label", {"horizontalAlignment": "HAlign_Center", "verticalAlignment": "VAlign_Center"})

    bp.var("TweenElapsed", "real")
    for b in spec["buttons"]:
        bp.function("Do" + b["id"], b["body"])
        bp.bind_click(b["id"])
    keys = ""
    pc = "(Game|GetPlayerController 0)"
    if spec.get("accept_key"):
        keys += f'''
  (if (and (> t 0.1) (Game|Player|WasInputKeyJustPressed :self {pc} :Key "{spec["accept_key"]}"))
    (CallFunction|Do{spec["buttons"][0]["id"]}))'''
    if spec.get("dismiss_key"):
        keys += f'''
  (if (and (> t 0.1) (Game|Player|WasInputKeyJustPressed :self {pc} :Key "{spec["dismiss_key"]}"))
    (CallFunction|{spec["dismiss"]}))'''
    events = tween_fade_dsl(spec["name"], "Panel", 0.2, focus=spec["buttons"][0]["id"], tick_extra=keys)
    for b in spec["buttons"]:
        events += f'''
(event OnClicked({b["id"]})
  (Development|PrintString "UI_{spec["name"]}_{b["id"]}_CLICKED")
  (CallFunction|Do{b["id"]}))'''
    bp.graph(events)
    bp.compile()
    return bp


CLOSE_TO_GAME = """
  (bind pc (Game|GetPlayerController 0))
  (Widget|RemovefromParent :self self)
  (Input|SetInputModeGameOnly :PlayerController pc)
  (Class|PlayerController|SetShowMouseCursor :self pc :bShowMouseCursor false)
  (Game|SetGamePaused false)"""


def open_menu_dsl(widget_class, marker, pause):
    """Statements that show a menu: viewport, GameAndUI input (keeps key polling alive), cursor, pause."""
    return f"""
  (bind pc (Game|GetPlayerController 0))
  (bind w (UserInterface|CreateWidget :Class "{widget_class}" :OwningPlayer pc))
  (UserInterface|Viewport|AddtoViewport :self w :ZOrder 10)
  (Input|SetInputModeGameAndUI :PlayerController pc :InWidgetToFocus w)
  (Class|PlayerController|SetShowMouseCursor :self pc :bShowMouseCursor true)
  (Game|SetGamePaused {"true" if pause else "false"})
  (Development|PrintString "{marker}")"""


def boot_actor(folder, name, code, level):
    """One boot actor per screen. Placed in the level only for its own test, then removed."""
    path = f"{folder}/{name}.{name}"
    if not must("Asset", "exists", {"path": path}):
        must("BP", "create", {"folder_path": folder, "asset_name": name, "asset_type": ref("/Script/Engine.Actor")})
    must("BP", "write_graph_dsl", {"graph": path + ":EventGraph", "code": code})
    return path


def ensure_level(level):
    """load_level refuses when the open level is dirty, so skip it when the level is already open."""
    cur = must("Scene", "get_current_level", {})
    if level not in str(cur):
        must("Scene", "load_level", {"level_path": level})


CONTENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "UnrealProject", "Content")


def _on_disk(path):
    rel = path.split(".")[0].replace("/Game/", "", 1)
    return os.path.exists(os.path.join(CONTENT, rel + ".uasset"))


def delete_assets(paths, timeout=120):
    """Delete assets so a following create cannot collide. Order dependents first.

    Right after editor launch the asset registry is still scanning: Asset.exists returns False for
    assets that are on disk, and the next create fails with "already exists". Disk is the truth here.
    """
    for path in paths:
        end = time.time() + timeout
        while _on_disk(path) and not must("Asset", "exists", {"path": path}):
            if time.time() > end:
                raise Fail(f"{path} is on disk but the asset registry never listed it")
            time.sleep(2)
        if must("Asset", "exists", {"path": path}) and not must("Asset", "delete", {"path": path}):
            raise Fail(f"Asset.delete returned False for {path}")
        if must("Asset", "exists", {"path": path}) or _on_disk(path):
            raise Fail(f"{path} still exists after delete")


def xform(x=0, y=0, z=0, yaw=0):
    # Keys other than location/rotation/scale (e.g. translation, scale3D) are ignored without an error.
    return {"location": {"x": x, "y": y, "z": z}, "rotation": {"pitch": 0, "yaw": yaw, "roll": 0},
            "scale": {"x": 1, "y": 1, "z": 1}}


def place(level, bp_path, label, loc=(0, 0, 0)):
    """Ensure one instance of bp_path is in the level at loc; returns its ref."""
    ensure_level(level)
    cls = ref(bp_path + "_C")
    found = must("Scene", "find_actors", {"root": None, "name": "", "actor_type": cls, "tag": "",
                                          "bounds": None, "collision_channels": []})
    if found:
        actor = found[0] if isinstance(found[0], dict) else ref(found[0])
        must("Actor", "set_actor_transform", {"actor": actor, "worldspace": True, "xform": xform(*loc)})
    else:
        actor = must("Scene", "add_to_scene_from_class", {"actor_type": cls, "name": label, "xform": xform(*loc),
                                                          "parent": None, "snap_to_ground": False})
    got = must("Actor", "get_actor_transform", {"actor": actor})["location"]
    if any(abs(got[k] - v) > 0.01 for k, v in zip("xyz", loc)):
        raise Fail(f"{label} at {got}, wanted {loc}")
    return actor


def unplace(level, bp_path):
    if not must("Asset", "exists", {"path": bp_path}):
        return
    ensure_level(level)
    for a in must("Scene", "find_actors", {"root": None, "name": "", "actor_type": ref(bp_path + "_C"), "tag": "",
                                           "bounds": None, "collision_channels": []}) or []:
        must("Scene", "remove_from_scene", {"actor": a} if isinstance(a, dict) else {"actor": ref(a)})
