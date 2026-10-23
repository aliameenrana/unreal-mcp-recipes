# UI recipe (UMG)

Builds themed, animated UMG menus in Unreal Engine 5.8 through Epic's Unreal
MCP server (`ModelContextProtocol` plugin). The calls, formats and node IDs
were run against a live 5.8 editor (evidence in [PROBES.md](PROBES.md)),
except items marked *(listed, not run)*: those were found with
`find_node_types` or in the tool schema but not executed yet. The pause
menu below has not been built end to end yet.

First target: a pause menu. The same sequences build an interaction prompt,
main menu, game-over screen or HUD.

## Requirements

- UE 5.8 project with these plugins enabled: `ModelContextProtocol`,
  `ToolsetRegistry`, `EditorToolset`, `UMGToolSet`, `SlateInspectorToolset`,
  `PythonScriptPlugin`.
- Server settings in `Config/DefaultEditorPerProjectUserSettings.ini`:

  ```ini
  [/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
  bAutoStartServer=True
  ServerPortNumber=8000
  ServerUrlPath=/mcp
  bEnableToolSearch=True
  ```

- With tool search on, the server lists three tools: `list_toolsets`,
  `describe_toolset`, `call_tool`. Everything below goes through
  `call_tool {toolset_name, tool_name, arguments}`.

## Calling conventions

| Toolset ID | Short name |
| --- | --- |
| `UMGToolSet.UMGToolSet` | UMG |
| `editor_toolset.toolsets.object.ObjectTools` | Object |
| `editor_toolset.toolsets.blueprint.BlueprintTools` | BP |
| `editor_toolset.toolsets.asset.AssetTools` | Asset |
| `editor_toolset.toolsets.scene.SceneTools` | Scene |
| `EditorToolset.EditorAppToolset` | App |
| `EditorToolset.LogsToolset` | Logs |
| `SlateInspectorToolset.SlateInspectorToolset` | Slate |

- UMG and App arguments are camelCase. Python toolsets (Object, BP, Asset,
  Scene) are snake_case.
- Objects and classes are passed as `{"refPath": "..."}`. Blueprint classes
  end in `_C`: `/Game/UI/WBP_Pause.WBP_Pause_C`.
- Send every parameter in the schema, including ones with a Python default.
  `find_node_types` fails without `"context_pins": []`.
- Widget refs are flat: `<WBP>:WidgetTree.<WidgetName>`, never nested under
  the parent's name. Slot refs: `<WBP>:WidgetTree.<Parent>.CanvasPanelSlot_<n>`
  (take them from the `slot` field `AddWidget` returns).
- `Object.set_properties` takes `values` as a JSON **string**. Property names
  vary per widget class; run `Object.list_properties` once per widget class
  before writing. A wrong name fails without an error.

## Property formats

Writing part of a nested struct merges: fields you leave out keep their value.

| Property | Format |
| --- | --- |
| Text (`text`) | `"Paused"` |
| Color (`colorAndOpacity`, brush `tintColor`) | `{"specifiedColor": {"r": 1, "g": 0.5, "b": 0.1, "a": 1}, "colorUseRule": "UseColor_Specified"}` |
| Font (`font`) | `{"fontObject": "/Engine/EngineFonts/Roboto.Roboto", "typefaceFontName": "Bold", "size": 48}` |
| Canvas slot (`layoutData`) | `{"offsets": {"left", "top", "right", "bottom"}, "anchors": {"minimum": {"x", "y"}, "maximum": {"x", "y"}}, "alignment": {"x", "y"}}`; with equal min and max anchors, offsets are position (left, top) and size (right, bottom) |
| Brush (Border `background`; Button `widgetStyle.normal`, `.hovered`, `.pressed`, `.disabled`) | `{"drawAs": "RoundedBox", "tintColor": <color>, "outlineSettings": {"cornerRadii": {"x", "y", "z", "w"}, "roundingType": "FixedRadius", "width": 0}}` |
| Padding (Border `padding`, Button `widgetStyle.normalPadding`) | `{"left", "top", "right", "bottom"}` |

Fonts: engine fonts only. `/Engine/EngineFonts/Roboto.Roboto` with typeface
`Bold` is verified; read other typeface names from the font asset before
using them. No MCP tool imports `.ttf` files. To use
a custom font, import it in the editor by hand once and reference the Font
asset path in the theme.

## Graph DSL

Graph logic is written with `BP.write_graph_dsl {graph, code}`, a Lisp-style
language. Call `BP.get_graph_dsl_docs {}` once per session for the full syntax.

- Node IDs come from `BP.find_node_types {graph, type_id_filter, context_pins: []}`;
  pin names from `BP.get_node_type_pins {graph, type_id}`. Guessed IDs fail.
- Bare names are only event parameters and `bind` locals. Read a member
  variable with `(Variables|Default|GetX)` and write it with
  `(Variables|Default|SetX v)`. A widget exposed as a variable is read with
  `(Variables|<WBPName>|Get<Widget>)`. Filtering for `GetLabel` also returns
  `ToolMenus|GetLabel`; use the `Variables|` entry.
- A write replaces only the events it names. Other events in the graph stay.
  Each sequence owns its events and never rewrites another sequence's.
- `write_graph_dsl` compiles the Blueprint. `BP.read_graph_dsl {graph}` reads
  it back; arguments equal to pin defaults are omitted from the read-back.
- `BP.add_variable {blueprint, name, type_name, graph: null, container_type: null}`:
  `"real"` and `"float"` both create a double.

Verified IDs:

| Purpose | ID |
| --- | --- |
| Widget events | `UserInterface\|EventConstruct`, `UserInterface\|EventTick (MyGeometry InDeltaTime)` |
| Actor event | `AddEvent\|EventBeginPlay` |
| Button event (after `BindToEventProperty`) | `OnClicked(Btn)`, `OnHovered(Btn)`, `OnPressed(Btn)` |
| Opacity | `Widget\|SetRenderOpacity :self :InOpacity` |
| Math | `Math\|Float\|Clamp(Float)`, `Math\|Float\|Min(Float)`; `Math\|Float\|Lerp`, `Math\|Float\|FInterpEaseinOut` *(listed, not run)* |
| Show | `UserInterface\|CreateWidget :Class :OwningPlayer`, `UserInterface\|Viewport\|AddtoViewport :self :ZOrder` |
| Hide | `Widget\|RemovefromParent` *(listed, not run)* |
| Player | `Game\|GetPlayerController` |
| Input mode | `Input\|SetInputModeUIOnly :PlayerController :InWidgetToFocus`; `Input\|SetInputModeGameOnly`, `Input\|SetInputModeGameAndUI` *(listed, not run)* |
| Cursor | `Class\|PlayerController\|SetShowMouseCursor :self :bShowMouseCursor` |
| Game | `Game\|SetGamePaused`, `Game\|QuitGame` *(listed, not run)* |
| Debug marker | `Development\|PrintString` |

## Sequences

### seq_ui_theme

Input: style words from the user, or none.

1. With no style given, propose a theme and get one confirmation.
2. Write `theme.json` in the shape of [theme.example.json](theme.example.json):
   colors, font, sizes, spacing, radius, button states.
3. Check every color channel is 0 to 1 and the font asset exists
   (`Asset.exists {path}`).

Done when the file parses and the font path resolves.

### seq_create_widget_layout

Input: widget name, folder, a layout tree (class, name, slot settings per node).

1. `Asset.exists {path}`; stop if the name is taken.
2. `UMG.CreateWidgetBlueprint {folderPath, assetName, parentClass: {"refPath": "/Script/UMG.UserWidget"}}`.
3. `UMG.AddWidget {widgetBlueprint, widgetClass, widgetDisplayName, parentWidget}`
   for each node, root first (no `parentWidget` makes the root). Keep the
   returned `widget` and `slot` refs.
4. `UMG.ToggleWidgetAsVariable {widgetBlueprint, widget, bIsVariable: true}`
   on every widget a graph will touch (buttons, changing text, tweened panels).
5. `Object.set_properties` on each slot with `layoutData`.

Done when `UMG.GetWidgetDescription {widgetBlueprint}` matches the tree.

### seq_style_widget

Input: widget Blueprint, `theme.json`, a role per widget (title, body, panel,
primary_button, danger_button).

1. Map each role to theme values.
2. `Object.set_properties` with the formats above: text color, font and size;
   border background and padding; button `widgetStyle` states.
3. `Object.get_properties {instance, properties}` on each and compare.

Done when every read-back equals the theme value.

### seq_bind_button

Input: widget Blueprint, button name, action (resume, quit, open level, open
widget, call a function).

1. `UMG.BindToEventProperty {widgetBlueprint, eventName: "OnClicked", propertyName: <button>, propertyClass: {"refPath": "/Script/UMG.Button"}}`.
2. Look up the action's node IDs and pins.
3. `BP.write_graph_dsl` with `(event OnClicked(<button>) ...)`, ending with a
   `PrintString` marker such as `"UI_<WBP>_<button>_CLICKED"`.

Done when `UMG.CompileWidgetBlueprint` returns true and `read_graph_dsl`
shows the handler.

### seq_tween_widget

Input: widget Blueprint, target widget, property (opacity, translation,
scale), from, to, duration, easing, loop flag.

1. `BP.add_variable` for `TweenElapsed`, `TweenDuration`, `TweenFrom`,
   `TweenTo` (`real`) and `TweenActive` (`bool`, *listed, not run*; confirm
   the type with `get_node_type_pins` on its getter).
2. Start the tween from `UserInterface|EventConstruct` or a function: set
   from, to, duration, `TweenElapsed = 0`, `TweenActive = true`.
3. In `UserInterface|EventTick`: if active, add the **capped** delta
   `(Math|Float|Min(Float) InDeltaTime 0.0333)`, compute
   `alpha = Clamp(elapsed / duration, 0, 1)`, ease it (ease-out:
   `1 - (1 - a)^2`), lerp from/to, set the property on the target. At
   alpha 1, clear `TweenActive` or reset elapsed when looping.

The cap matters: the first tick after a widget is created carries a ~0.3 s
hitch, which otherwise finishes a short tween in one frame.

Done when the widget compiles and a PIE run shows the tween taking
`duration / 0.0333` frames or more. Count frames from the log's
`[frame]` field, not wall-clock: a backgrounded editor runs at ~3 fps.

Example (opacity fade over 0.3 s):

```lisp
(event UserInterface|EventTick (MyGeometry InDeltaTime)
  (bind t (+ (Variables|Default|GetTweenElapsed) (Math|Float|Min(Float) InDeltaTime 0.0333)))
  (Variables|Default|SetTweenElapsed t)
  (Widget|SetRenderOpacity :self (Variables|WBP_Pause|GetPanel)
    :InOpacity (Math|Float|Clamp(Float) (/ t 0.3) 0.0 1.0)))
```

### seq_show_widget

Input: widget Blueprint, trigger (BeginPlay or a key), input mode, pause flag.

1. Create the boot actor once: `BP.create {folder_path, asset_name: "BP_UIBoot", asset_type: {"refPath": "/Script/Engine.Actor"}}`.
   Never edit template Blueprints to show UI.
2. `BP.write_graph_dsl` on `BP_UIBoot:EventGraph`:

   ```lisp
   (event AddEvent|EventBeginPlay
     (bind pc (Game|GetPlayerController 0))
     (bind w (UserInterface|CreateWidget :Class "/Game/UI/WBP_Pause.WBP_Pause_C" :OwningPlayer pc))
     (UserInterface|Viewport|AddtoViewport :self w :ZOrder 0)
     (Input|SetInputModeUIOnly :PlayerController pc :InWidgetToFocus w)
     (Class|PlayerController|SetShowMouseCursor :self pc :bShowMouseCursor true))
   ```

   The hide path mirrors it: `Widget|RemovefromParent`,
   `Input|SetInputModeGameOnly`, cursor off, `Game|SetGamePaused false`
   *(listed, not run)*. Triggering from a key instead of BeginPlay is not
   probed yet.
3. Make sure the level is loaded: the editor opens on a temp level.
   `Scene.load_level {level_path}`, then
   `Scene.add_to_scene_from_class {actor_type: {"refPath": ".../BP_UIBoot.BP_UIBoot_C"}, name, xform: {translation, rotation (quaternion), scale3D}, parent: null, snap_to_ground: false}`
   if no instance exists.

Done when the boot actor compiles and exactly one instance is in the level.

### seq_verify_widget

1. `UMG.CompileWidgetBlueprint` on every widget. `BP_UIBoot` is compiled by
   `write_graph_dsl`; `BP.compile_blueprint` exists for a manual recompile
   *(listed, not run)*.
2. `Asset.save_assets {asset_paths}` on everything created *(listed, not
   run)*. Compiling does not save.
3. `App.StartPIE {"options": {"bSimulate": false, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}}`.
4. `App.CaptureEditorImage {}`: the PNG is base64 in `returnValue.data` and
   shows UMG. (`CaptureViewport` needs a camera transform and renders the
   scene without UI; do not use it for menus.)
5. For each button: `Slate.Observe {"ref": "", "maxDepth": 60}` once, then
   `Slate.Snapshot {"ref": "", "maxDepth": 60, "bIncludeSourceLocations": false}`
   and find `button "<label>" [...] [ref=bNN]`; `Slate.Hover {ref}`,
   `Slate.Click {ref, "button": "left", "doubleClick": false}`. Refs change
   every PIE session. The snapshot is long; filter it for the label.
6. Wait ~1 s, then `Logs.GetLogEntries {"category": "LogBlueprintUserMessages", "pattern": "<marker>", "maxEntries": 20}`.
   A read straight after the click comes back empty.
7. `App.StopPIE {}`.

Done when the capture shows the widget and every expected marker is in the
log.

## Pause menu

1. `seq_ui_theme`.
2. `seq_create_widget_layout` `WBP_Pause`: CanvasPanel `Root` > Border
   `Dim` (full screen: anchors 0,0 to 1,1, offsets 0) > VerticalBox `Panel`
   (centered) > TextBlock `Title`, Button `Resume` (TextBlock child),
   Button `Quit` (TextBlock child).
3. `seq_style_widget`: `Dim` = background at 0.6 alpha, `Title` = title
   size, `Resume` = primary_button, `Quit` = danger_button.
4. `seq_bind_button`: `Resume` runs the hide path, `Quit` runs `Game|QuitGame`.
5. `seq_tween_widget`: `Panel` opacity 0 to 1 over 0.2 s, ease-out, started on
   Construct.
6. `seq_show_widget`: toggled by the Escape key, UI-only input, game paused.
7. `seq_verify_widget`, clicking `Resume` and checking the menu closed.

## Out of scope

CommonUI and gamepad focus, settings menus saved to Game User Settings,
runtime theme switching, UMG Sequencer animations, MVVM bindings, custom
font import.
