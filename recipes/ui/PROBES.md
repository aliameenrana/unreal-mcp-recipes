# UI recipe probes

Evidence behind [RECIPE.md](RECIPE.md). Each probe tested one tool route
against a live UE 5.8 editor with Epic's MCP server, in a scratch folder
that was deleted afterwards. The probe definitions are as planned before
running; the results section records what actually happened and overrides
the definitions where they differ (for example, P7 ended up using
`CaptureEditorImage`, and custom font import in P3 was dropped).

## Probe definitions

Run in order in a scratch folder `/Game/_Probe/UI`. Delete the folder after
the last probe. Record each result (PASS, FAIL, or the workaround found) in
the results section below. A FAIL stops the steps that depend on it;
it does not stop the other probes.

**P0. Server and toolset IDs.** Open the project, wait for shaders, then
`tools/list` (expect `list_toolsets`, `describe_toolset`, `call_tool`),
`list_toolsets`, and `describe_toolset` on the six toolsets above.
Pass: all six are listed. Write down the exact IDs and the argument format
`call_tool` expects; everything after this uses them.

**P1. Widget tree.** `CreateWidgetBlueprint("/Game/_Probe/UI", "WBP_Probe", UserWidget)`,
then `AddWidget` a `CanvasPanel` with no parent (becomes root), then a
`TextBlock` under it. `GetWidgetDescription`. Pass: the tree shows
CanvasPanel > TextBlock.

**P2. Property formats.** On the TextBlock: `list_properties`, then
`set_properties` for text, color and font size; on its slot: anchors,
position, size, alignment. On a `Border`: brush color and padding.
`get_properties` each back. Pass: every value reads back as written. Record
the exact JSON shape for `FText`, `FSlateColor`, `FSlateFontInfo`, `FMargin`,
`FAnchors`, `FVector2D`. This table is what the styling sequence uses.

**P3. Font.** Set the font to the engine's Roboto
(`/Engine/EngineFonts/Roboto.Roboto`) with typeface `Bold`. Then try one
imported `.ttf` through the import path in `asset.py` (`import_asset`).
Pass for Roboto is required. Custom font import is optional; on FAIL the
theme is limited to engine fonts.

**P4. DSL on a widget graph.** `list_graphs` on `WBP_Probe`, get the event
graph, `find_node_types` with filter `Tick`, `get_node_type_pins` on the
result, then `write_graph_dsl` an `(event Tick ...)` that sets the
TextBlock's render opacity from a float variable. Run `read_graph_dsl`
afterwards. Then call `write_graph_dsl` a second time with a different
function and read back again. Pass: both compile, and the second read shows
whether the first write survived (replace vs append). Record which.

**P5. Button event.** Add a `Button`, `ToggleWidgetAsVariable(true)`,
`BindToEventProperty(WBP, "OnClicked", <button name>, Button)`, then
`read_graph_dsl` to see how the bound event is named, and fill it with
`(Development|PrintString "clicked")`. Pass: compiles and the event body is
there on read-back.

**P6. Show on screen.** `BlueprintTools.create` an Actor Blueprint
`BP_Probe_UIBoot`. In its event graph, BeginPlay: Create Widget
(`WBP_Probe`), Add to Viewport, and the input-mode and show-cursor nodes,
all found with `find_node_types`. Place it in `L_OcclusionTest`. A fresh
actor keeps the template's `BP_ThirdPersonCharacter` graph untouched.
Pass: compiles.

**P7. Verify in PIE.** `StartPIE` with a warmup of 2 seconds, then
`CaptureViewport`, then `GetLogEntries` filtered for a PrintString marker
written on BeginPlay, then `StopPIE`. Pass: the capture shows the widget. If
the capture does not include UMG, try `CaptureEditorImage`. If neither shows
it, verification falls back to log markers only, and section 4's checks
change to match.

**P8. Tween timing.** Use the P4 Tick graph to fade opacity 0 to 1 over
0.3 s and print a marker when done. In PIE, read the log time between the
start and done markers. Pass: within one frame of 0.3 s.

## Results (2026-10-24, UE 5.8)

Probe assets were deleted afterwards. These results override anything above
that disagrees.

**Calling convention.** `call_tool` takes `toolset_name`, `tool_name`,
`arguments`. Toolset IDs: `UMGToolSet.UMGToolSet`,
`editor_toolset.toolsets.object.ObjectTools`,
`editor_toolset.toolsets.blueprint.BlueprintTools`,
`editor_toolset.toolsets.asset.AssetTools`,
`editor_toolset.toolsets.scene.SceneTools`,
`EditorToolset.EditorAppToolset`, `EditorToolset.LogsToolset`. UMG and
EditorApp arguments are camelCase; Python toolset arguments are snake_case.
Objects and classes are `{"refPath": "..."}`; Blueprint classes end in `_C`.
Every parameter in the schema must be sent, including ones with a Python
default (`find_node_types` needs `"context_pins": []`).

**Widgets (P1).** Widget refs are `<WBP path>:WidgetTree.<Name>`, slot refs
`<WBP path>:WidgetTree.<Parent>.CanvasPanelSlot_<n>`. `AddWidget` with no
parent makes the root.

**Property formats (P2, P3).** `set_properties` takes `values` as a JSON
string. Partial nested writes merge; unspecified fields keep their values.
- Text: `"text": "Paused"`.
- Color: `{"specifiedColor": {"r","g","b","a"}, "colorUseRule": "UseColor_Specified"}`.
- Font: `{"fontObject": "/Engine/EngineFonts/Roboto.Roboto", "typefaceFontName": "Bold", "size": 48}`.
- Canvas slot: `layoutData` = `{offsets: {left, top, right, bottom}, anchors: {minimum: {x, y}, maximum: {x, y}}, alignment: {x, y}}`, plus `bAutoSize`. Offsets mean position and size while min and max anchors are equal.
- Brush (Border `background`, Button `widgetStyle.normal|hovered|pressed|disabled`): `{"drawAs": "RoundedBox", "tintColor": <color>, "outlineSettings": {"cornerRadii": {x, y, z, w}, "roundingType": "FixedRadius", "width": 0}}`.
- Border `padding` and button `normalPadding`: `{left, top, right, bottom}`.
- Custom font import was not probed; the theme uses engine fonts for now.

**Variables.** `add_variable(type_name="real")` and `"float"` both create a
double. Confirm a type with `get_node_type_pins` on its getter.

**Graph DSL (P4, P5, P6).**
- Use exact node IDs from `find_node_types`; guessed IDs fail.
- Event IDs: `UserInterface|EventConstruct`, `UserInterface|EventTick (MyGeometry InDeltaTime)`, `AddEvent|EventBeginPlay` for actors. A button event made by `BindToEventProperty` is `(event OnClicked(Btn))`.
- Bare names are only locals and event params. Read members with `(Variables|Default|GetX)`, write with `(Variables|Default|SetX v)`. Widget members are `(Variables|<WBP name>|Get<Widget>)` (filtering for `GetLabel` also returns `ToolMenus|GetLabel`; take the `Variables|` one).
- A write replaces only the events it names; other events stay. Each sequence owns its events.
- Writes compile. Read-back drops arguments that equal pin defaults.
- Node IDs used: `Widget|SetRenderOpacity`, `Math|Float|Clamp(Float)`, `Math|Float|Min(Float)`, `Math|Float|Lerp`, `Math|Float|FInterpEaseinOut`, `UserInterface|CreateWidget (:Class :OwningPlayer)`, `UserInterface|Viewport|AddtoViewport (:self :ZOrder)`, `Widget|RemovefromParent`, `Game|GetPlayerController`, `Input|SetInputModeUIOnly (:PlayerController :InWidgetToFocus)`, `Input|SetInputModeGameOnly`, `Input|SetInputModeGameAndUI`, `Class|PlayerController|SetShowMouseCursor (:self :bShowMouseCursor)`, `Game|SetGamePaused`, `Game|QuitGame`, `Development|PrintString`.

**Level and PIE (P6, P7).** The editor opens `/Temp/Untitled_1`; call
`SceneTools.load_level("/Game/MCPTest/L_OcclusionTest")` first. Place actors
with `SceneTools.add_to_scene_from_class(actor_type, name, xform, parent, snap_to_ground)`,
xform `{translation, rotation (quat), scale3D}`. `L_OcclusionTest` spawns a
DefaultPawn, not the Third Person character. Verification:
`StartPIE {"options": {"bSimulate": false, "playMode": "PlayMode_InViewPort", "warmupSeconds": 2}}`,
then `CaptureEditorImage` (shows UMG; the PNG is base64 in
`returnValue.data`), then `GetLogEntries {"category": "LogBlueprintUserMessages", "pattern": "<marker>"}`,
then `StopPIE`. `CaptureViewport` requires a camera transform and was not used.

**Tween timing (P8).** The first tick after a widget is created carries a
~0.3 s hitch and finished a 0.3 s tween in one frame. `seq_tween_widget`
caps the delta: `(Math|Float|Min(Float) InDeltaTime 0.0333)`. With the
cap the fade took 8 to 9 frames. A backgrounded editor runs at ~3 fps, so
check tweens by frame count or game time, not log wall-clock.

**Button click in PIE (verified).** `SlateInspectorToolset` (enabled in the
uproject for this) drives real Slate input. During PIE:
`Observe {"ref": "", "maxDepth": 60}`, then `Snapshot` (same args plus
`"bIncludeSourceLocations": false`) and find the line
`button "<label>" [pos=..] [ref=bNN]`, then `Hover {"ref"}`, then
`Click {"ref", "button": "left", "doubleClick": false}`. Wait ~1 s before
`GetLogEntries`; a log read straight after the click returned nothing. Result:
OnHovered, OnPressed and OnClicked handlers all fired. Refs change every
PIE session; take them from a fresh Snapshot. Snapshot output is long, so
filter it instead of reading it whole.

**Custom fonts: dropped.** No MCP tool imports `.ttf`, and a headless
editor import crashed. Themes use engine fonts (Roboto).
