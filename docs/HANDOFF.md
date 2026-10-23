# Handoff: Unreal sequences and recipes on top of Epic's MCP

This file starts a new project. Read all of it before writing anything.

## 1. What this project is

A library of **sequences** and **recipes** that teach an AI agent how to build
things in the Unreal Editor (UE 5.8) through **Epic's own MCP server**.

The agent already has tools: Epic's MCP gives it calls like "add a node to a
Blueprint graph" or "spawn an actor." What it lacks is the knowledge of which
calls to make, in what order, with which arguments, which ones fail silently,
and how to prove the result worked. Without that knowledge an agent guesses,
fails, retries, and burns tokens. This project supplies that knowledge in a
form the agent loads only when the task needs it.

The product is the workflow knowledge. It is not a tool server.

## 2. The old tool server: do not use it

An earlier project built its own MCP server with 131 tools:

- Repo: `github.com/aliameenrana/unreal-mcp-agent`
- Tool code: `src/unreal_mcp/tools/`
- Tool catalog: `PLAN.md` and `TOOL_BUILDING_GUIDE.md`
- First draft of the sequences: `SEQUENCE_DESIGNS.md`

**This new project does not use those tools.** Every sequence targets Epic's
MCP only. The old repo is reference material for one reason: the engine
behavior it recorded (section 6) was confirmed live against a running 5.8
editor, and most of those facts are about the engine, not about the old
tools. Read `SEQUENCE_DESIGNS.md` for the sequence ideas. Ignore its tool
names. Every step in it names a tool from the old server, and all of those
names have to be replaced with Epic MCP calls.

## 3. Sequences and recipes, defined

### Sequence

A sequence is one small, complete authoring job with a fixed order of tool
calls and a check at the end that proves it worked. Example: "add an
`UpdatePerception` function to a character Blueprint that sets `CanSeeTarget`
and `InAttackRange` from the distance to a target."

A sequence:

- **builds something in the editor.** A Blueprint, a graph function, a
  variable, a widget, an attached prop, a level layout.
- **does not play the game.** It is editor-time construction. "Fire a
  projectile" is gameplay and is never a sequence. "Build the Blueprint that
  fires a projectile when the game runs" is a sequence.
- **runs with no human.** No clicking in the editor, no dialog to dismiss. The
  one accepted exception is getting an asset that does not exist in the
  project (section 8).
- **ends with an independent read-back.** The agent checks the result with a
  separate read call: compile the Blueprint and read its error list, list the
  graph's nodes and their connections, read the property back. It never
  trusts the return value of the call that made the change. Section 6 lists
  real cases where a call reported success and the result was wrong.

### Recipe

A recipe is a named bundle of sequences plus the glue that orders them and
passes outputs from one to the next. "Build a patrolling enemy that chases
and attacks the player" is a recipe made of six sequences: find a character
asset, find its animations, wire perception logic, drive animation by state,
attach a weapon, verify the whole build.

The recipe states what the user supplies (character description, ranges,
attack type) and what each sequence hands to the next (the resolved asset
path, the skeleton, the variable names).

### Agent abilities

On top of recipes, the agent needs to:

1. **Pick a recipe** from a plain request ("make me an enemy that guards this
   door") and fill in its inputs.
2. **Chain recipes** when a request spans several ("enemy with a sword and a
   health bar" means the enemy, weapon and UI recipes).
3. **Recover from a failed step** by checking that sequence's known traps
   first, before trying anything new.
4. **Report honestly**: what was built, what was verified and how, and what
   was cut (for example "states switch animation instantly, no blending").

## 4. Format of one sequence

Every sequence file has these parts, in this order:

```
# seq_wire_perception_logic

Goal: one sentence naming what exists in the editor afterwards.

Inputs: what must be supplied (Blueprint path, target variable name, ranges).
Preconditions: what must already be true, and how to check each one.
Outputs: what later sequences can rely on (variable names, graph name).

Steps:
  1. Capability needed, then the Epic MCP call that provides it, with arguments.
  2. ...

Traps: the specific ways this goes wrong, and the fix for each.
  - Comparison nodes such as Less_FloatFloat build as untyped wildcard nodes.
    Use KismetMathLibrary.InRange_FloatFloat instead.

Verify: the read calls that prove success, and the exact values expected.

Ceiling: what this sequence cannot do, stated plainly.
```

Two rules for the steps:

- **Name the capability first, then the Epic MCP call.** For example,
  "add a call-function node to a graph, using `<Epic tool name>`." When Epic
  renames a tool, only one place in a mapping file needs to change.
  Keep that mapping in one file (`capabilities.md` or similar): one row per
  capability, the Epic MCP call that provides it, and a link to its doc.
- **No step may be a guess.** Every call and argument shape comes from Epic's
  docs, then gets confirmed once against the live editor. If the docs don't
  cover it, mark the step `UNCONFIRMED` until a live test settles it.

## 5. How to deliver it

Recommended: one Claude Code **skill** per recipe, packaged as a plugin.

- Each skill has a short description so the agent loads it only when the
  request matches. The agent doesn't carry 40 workflows in context at once.
- Each skill's folder holds the recipe file and its sequence files.
- One shared file holds the capability mapping and the global traps list
  (section 6), so they aren't repeated in every skill.

## 6. Engine behavior already confirmed live

These were found by running real calls against a live UE 5.8 editor. Most
are engine behavior, so they probably still hold under Epic's MCP. Recheck
each one once there before relying on it.

**Blueprint graphs**

- **Comparison operators become wildcard nodes.** `Less_FloatFloat`,
  `Greater_FloatFloat`, `EqualEqual_*` and the other basic comparisons all
  create a `K2Node_PromotableOperator` whose pin types stay unresolved. Only
  a human dragging a wire in the editor resolves them. Setting a pin's value
  does not. The node still gets created, and the old tool reported success.
  Fix: `KismetMathLibrary.InRange_FloatFloat` (Value, Min, Max,
  InclusiveMin, InclusiveMax in, bool out) is a normal, fully typed node.
  Detect the problem by reading back each node's class.
- **AND is safe.** `BooleanAND` builds as a
  `K2Node_CommutativeAssociativeBinaryOperator` with real Boolean pins, so
  the wildcard trap above does not apply to it.
- **Variable types fail silently.** `BlueprintEditorLibrary.get_basic_type_by_name`
  accepts only `int`, `byte`, `bool`, `real`, `name`, `string`, `text`. Any
  other name (including `float` and `object`) quietly returns an int type.
  Floats are `real`. Object and actor references need
  `get_object_reference_type(class)`. Read the variable's type back after
  creating it.
- **Renaming a node does not change its title.** Two nodes made from the same
  function have the same title forever. To address one, select by position
  or by the node's internal name, never by title alone.
- **`GetActorLocation` failed to add** as a call-function node
  (`'NoneType' object has no attribute 'get_node_title'`). Not root-caused.
  Test it again under Epic's MCP; it is needed for the line-of-sight trace.
- **Line trace:** `KismetSystemLibrary.LineTraceSingle` builds as "Line Trace
  By Channel": Start and End (Vector), TraceChannel, ActorsToIgnore, OutHit,
  and a bool return (true means something blocked the line).

**Animation**

- **AnimBP state machines cannot be authored from Python.** A StateMachine
  node can be added to an AnimGraph, but there is no way to create states,
  conduits or transitions inside it. Workaround used in the sequences: a
  Blueprint function picks the animation for the current state and swaps it
  on the instance. Cost: an instant cut between states, no blending. Check
  whether Epic's MCP exposes state creation. If it does, this ceiling goes
  away.
- **`AnimationStateMachineLibrary` is runtime only** (`get_state`,
  `set_state`). It does not edit graphs.
- **BlendSpaces are normal animation assets.** `SkeletalMeshComponent.set_animation`
  takes any `AnimationAsset`. The Third Person template's walk/run is
  `BS_Idle_Walk_Run`, a BlendSpace. After assigning one, drive it with
  `AnimSingleNodeInstance.set_blend_space_position(Vector)`. Otherwise it
  sits at its default corner (usually idle).

**Actors, levels, assets**

- **Blueprint classes need the `_C` suffix** to spawn:
  `/Game/.../BP_Thing.BP_Thing_C`.
- **A bare StaticMeshActor spawns with no mesh.** Assign one with
  `StaticMeshComponent.set_static_mesh(mesh)`.
- **New level from the Basic template:**
  `LevelEditorSubsystem.new_level_from_template(path, "/Engine/Maps/Templates/Template_Default")`.
  The `EditorLevelLibrary` version is deprecated. `/Engine/Maps/Templates/Thumbnails/Basic`
  is an image, not a map.
- **Deleting a Blueprint asset sometimes fails** and gives no reason, even
  after saving it first. Not root-caused. Name test assets so leftovers are
  easy to find.

**Areas with no Python path (do not design around them)**

- GAS setup (C++ only).
- Niagara graph and module authoring. Spawning and setting parameters on an
  existing Niagara system works.
- Creating Sequencer bindings (deadlocks the editor). Reading existing
  bindings works.
- Landscape sculpting. Heightmap import is the only route.

## 7. Sequence catalog

From `SEQUENCE_DESIGNS.md`. The ideas carry over; the tool names do not.

**Enemy AI (start here, the flagship recipe)**
- `seq_acquire_character_asset`: find a skeletal mesh or character Blueprint
  in the project that matches the description and check it has a skeleton.
- `seq_discover_or_import_animations`: find Idle, Patrol, Chase, Attack and
  Hit animations whose skeleton matches the character, as AnimSequence or
  BlendSpace.
- `seq_wire_perception_logic`: build the `UpdatePerception` function. It
  sets `InAttackRange` and `CanSeeTarget`; `CanSeeTarget` requires being in
  range and having an unblocked line trace. Event Tick calls it.
- `seq_drive_state_animation_by_instance_swap`: a second function picks the
  animation from those two variables and assigns it.
- `seq_attach_weapon_for_attack_type`: map the attack type to a weapon and a
  socket, check the socket exists on this skeleton, attach the weapon, read
  back the socket it landed on.
- `seq_verify_enemy_construction`: compile everything with zero errors,
  check the names match across sequences, then a short Play-in-Editor pass
  at four positions (out of range, chase range, attack range, behind a wall),
  reading the two variables at each.

**Inventory:** item schema (data table), inventory component Blueprint,
pickup actor, overlap wired to add to inventory.

**Weapons:** weapon data table, melee weapon actor, ranged weapon actor,
projectile Blueprint, fire function graph, projectile impact graph, hitscan
variant, attack combo graph, sheathe/draw toggle.

**Magic:** spell data table, cast function graph (cooldown, cost),
targeted vs area-of-effect branch.

**Health and scoring:** health pool, damage function, debuff timer, score
tracking, death function.

**UI (UMG):** HUD widget, inventory widget, interaction prompt widget,
adding and removing widgets from the viewport. Full plan with probes and
exact tool calls: `recipes/ui/RECIPE.md`. Two parts are required, not
optional:
- `seq_apply_ui_theme`: the user supplies (or the agent proposes) a theme
  spec: palette, font, font sizes, padding, corner radius. Store it once as
  a struct or data asset; every widget sequence reads from it. No hardcoded
  colors or sizes in individual widgets.
- `seq_tween_widget`: animations are code tweens, not UMG Sequencer
  animations (Sequencer bindings deadlocked the editor under the old tools).
  Widget Blueprints can't hold Timelines, so tweens run on Tick or a looping
  timer: accumulate elapsed time, ease the alpha, and set render opacity,
  render translation, render scale or color. Cover fade, slide, scale pop
  and a looping pulse. Looping effects can also run in a UI material driven
  by its Time node. If the UMG toolset can author Sequencer animations
  safely, that is an option, not a requirement.

**Vehicles:** vehicle actor on `ChaosWheeledVehicleMovementComponent`,
enter/exit graph, input bindings, default tuning. Most settings are plain
properties and can be set from script. Competitive tuning is out of scope.

**Level generation:** landscape prompt, heightmap import, foliage,
set dressing scatter, lighting mood.

**Cross-cutting:** `seq_resolve_asset_by_intent` decides where a missing asset
comes from (section 8).

Dropped from scope: VR, and Fab marketplace automation.

## 8. Getting assets

- Use what is already in the project first. The test project has the Third
  Person content pack.
- Sketchfab has a public API that can search and download, but models only
  (glTF), no animations.
- Fab and Mixamo have no API a script can use. Kenney assets are direct
  downloads with no search API.
- Animations are the one gap with no automated source. If a needed animation
  is missing, the sequence stops and asks the human for it.

## 9. Test project

Use `UnrealProject/SequencesTestProject.uproject` (kept out of git: 939 MB of assets). It is a
cleaned copy of the old project in that repo (leave that one
alone).

- **Epic MCP:** plugin `ModelContextProtocol` ("Unreal MCP", experimental,
  ships with 5.8 at `Engine/Plugins/Experimental/ModelContextProtocol`).
  Auto-start is on in `Config/DefaultEditorPerProjectUserSettings.ini`, so
  opening the editor serves `http://localhost:8000/mcp`. `.mcp.json` at the
  repo root points Claude Code at it.
- **Tool search is on** (`bEnableToolSearch`): `tools/list` returns only
  `list_toolsets`, `describe_toolset` and `call_tool`. Discover toolsets
  with those; don't expect every tool to be listed up front.
- **Toolsets enabled:** Editor, AIModule, AnimationAssistant, StateTree,
  UMG, DataRegistry, GameplayTags, Niagara, Physics, SemanticSearch,
  AutomationTest, ConfigSettings, SlateInspector (simulated UI clicks). Others (GAS, PCG, MetaHuman and more) are
  in `Engine/Plugins/Experimental/Toolsets`; enable one only when a recipe
  needs it.
- **Epic docs:** the plugin ships no docs. Its headers under `Source/` are
  the primary reference (settings, server, toolset registry). Check
  dev.epicgames.com for an Unreal MCP page before reading source.
- **Plugins removed:** Remote Control (only the old server used it). Python
  stays on.
- **Content:** Third Person template, `Characters/Mannequins`, `Input`,
  `LevelPrototyping`, `Guard` (a guard character pack with a weapon, a good
  first enemy candidate), `PoseAnimations` (extra animation set), and
  `MCPTest` (`L_OcclusionTest` plus Red/Green/Blue materials). The
  `ThirdPerson/Blueprints` assets were restored from the engine template, so
  everything the old tools built on `BP_ThirdPersonCharacter` (variables, the
  `UpdatePerception` function, junk variables) is gone. Scratch maps, probes
  and the `X` asset were deleted.
- **Not yet opened in the editor.** On first open, let shaders compile, then
  confirm the MCP server answers before anything else. Rebuild
  `L_OcclusionTest`'s actor list if the template restore broke a reference.

The old build's state, kept for reference only:

Test level `/Game/MCPTest/L_OcclusionTest`, made from the Basic template:
- `BP_ThirdPersonCharacter_C_0` (the enemy) at (0, 0, 100)
- `BP_ThirdPersonCharacter_C_1` (the target) at (300, 0, 100), rotated 180
- `StaticMeshActor_1` (a cube wall) at (150, 0, 150), between them

On `/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter`, built with the old
tools and compiling with zero errors:
- Variables `CanSeeTarget` (bool), `InAttackRange` (bool) and
  `PerceptionTargetActor` (Actor reference).
- Function `UpdatePerception`: get `PerceptionTargetActor`, then
  `GetDistanceTo`, which feeds two `InRange_FloatFloat` nodes (Max 150 for
  attack, Max 1500 for perception). The 150 node sets `InAttackRange`.
- **Wrong for now:** the 1500 node sets `CanSeeTarget` directly, so walls
  don't block sight yet.
- Placed but not wired: a Line Trace By Channel node, a `BooleanAND` node
  and a `Not_PreBool` node. The missing piece is `GetActorLocation` for the
  trace's Start and End.
- **Junk to remove:** variables `PerceptionTarget` and `PerceptionTargetCheck`
  (meant to be object references, came out as int). Scratch assets
  `/Game/MCPTest/BP_PerceptionProbe` and `BP_OcclusionProbe` may still
  exist.
- Not started: the animation-by-state function, the Event Tick hookup, the
  weapon attachment, and the Play-in-Editor verification.

It would be cleaner to rebuild this from scratch through Epic's MCP as the
first real test of the first sequence than to patch the old build.

## 10. Rules carried over from the old project

- **Docs first.** Read Epic's official documentation (and any Epic
  walkthrough) before calling an API. Live calls only confirm what the docs
  say. Open-ended trial and error wasted most of the tokens in the old
  project, and the user stopped it explicitly.
- **Spend tokens on decisions, not wandering.** The product teaches an agent
  to make good decisions; building it needs the same discipline. Read the
  docs first, decide the approach, then act. No rabbit holes: if something
  doesn't work after one documented attempt, write it down as `UNCONFIRMED`
  or a gap and move on rather than probing at random.
- **Read back every change** with a separate call. Section 6 has three cases
  where the call that made a change reported success while building the
  wrong thing.
- **Unconfirmed steps say so.** A sequence step that has not been checked
  against the docs and a live editor is marked `UNCONFIRMED`.
- **Build the whole recipe.** When the user asks for a working recipe, build
  it and verify it in a scene before reporting back. Don't stop after each
  small step to ask whether to continue.
- **No AI attribution** in commits, docs or code.
- **One editor connection at a time.** Two agent sessions driving the same
  editor through Remote Control interfered with each other. Run one at a
  time.

## 11. First tasks in the new repo

1. Read Epic's MCP documentation and list its tools. Write the capability
   mapping file. For each step in the Enemy AI recipe, mark it "Epic covers
   it", "Epic covers it differently" (describe how), or "gap."
2. Recheck each item in section 6 that the Enemy AI recipe depends on
   through Epic's MCP, against the docs first.
3. Write the six Enemy AI sequences in the section 4 format, then the recipe
   that chains them.
4. Run the recipe end to end in `L_OcclusionTest` until the Play-in-Editor
   check passes at all four positions.
5. Package it as the first skill. Do the next recipe only after this one
   works.
