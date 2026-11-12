# Level generation recipe

Generates a blockout level from an ASCII layout: floor tiles, walls, a player start, enemy spawn
markers, a seeded prop scatter and a lighting mood. Built through Epic's Unreal MCP, checked with
downward traces in the editor and with a character standing on the generated floor in Play-in-Editor.

## Run it

```bash
python3 recipes/level/build/level.py [--mood day|dusk|night] [--seed N] [--verify-only]
```

Defaults: `--mood dusk --seed 7`. Each run clears the `Generated` outliner folder and rebuilds, so there
is no `--fresh`. The run ends with `LEVEL PASS`. `--verify-only` re-runs the checks without regenerating.

## Inputs

| Input | Where | Meaning |
| --- | --- | --- |
| `LAYOUT` | `level.py` | `#` wall, `.` floor, `S` player start, `E` enemy spawn. Row 0 is +X, column 0 is -Y; the grid is centred on the origin. |
| `TILE`, `WALL_H`, `FLOOR_T` | `level.py` | 400, 300, 20 units. Floor tops sit at Z=0. |
| `PROPS`, `PROP_COUNT` | `level.py` | Crates (cube 0.8) and pillars (cylinder 0.6 x 1.6); 8 props. |
| `--seed` | CLI | The same seed always places the same props. |
| `--mood` | CLI | Sun pitch, intensity and colour, sky light intensity, fog density (`MOODS`). |

## What gets built

| Output | Contents |
| --- | --- |
| `/Game/Generated/L_Generated` | A copy of `/Engine/Maps/Templates/Template_Default` (sun, sky atmosphere, sky light, fog, clouds, player start). The template floor is removed. World settings game mode: the Guard pack's `BP_ThirdPersonGameMode` (pawn `BP_Guard`). |
| Outliner `Generated/Floor`, `Generated/Wall`, `Generated/Prop` | One static mesh actor per tile or prop, labelled `Floor_<row>_<col>`, `Wall_<row>_<col>`, `Prop_<kind>_<i>`. |
| Outliner `Generated/Spawns` | A `TargetPoint` per `E` cell, labelled `EnemySpawn_<i>` and tagged `EnemySpawn` for other recipes (for example the enemy recipe) to find. |
| `PlayerStart_0` | Moved to the `S` cell, raised by the pawn's capsule half height plus 2. |
| `/Game/Generated/BP_LevelProbe` | Test-only actor: R prints `LVL pawn=<location>`. Removed from the level after the test. |

Props avoid the 3 x 3 cells around `S` and `E` and any doorway (a floor cell with walls on two opposite
sides), and are offset up to 80 units inside their tile with a random yaw.

## Checks

- The labels in the `Generated` folder equal the plan exactly, so a regeneration leaves nothing stale.
- A trace from Z=2000 straight down through every wall and prop, and through every floor tile without a
  prop, hits within 1 unit of the planned top (300 for walls, 0 for floors, the prop's height for props).
- In PIE the pawn is within 50 units of the start cell, and its Z is the capsule half height plus 1.9 to
  2.4 (the gap CharacterMovement keeps above the floor), unchanged after 2 s.

Measured run: 47 floor tiles, 43 walls, 8 props, 90 traces; character at (1200, -1400, 90.0) with
capsule half height 88.

## Not covered

Landscape sculpting, heightmap import and foliage painting. No loaded MCP toolset creates or edits a
Landscape, and the programmatic toolset is a sandbox that can only call other tools. Enabling the
experimental `PCGToolset` plugin would be the route for in-engine scatter.

## Traps found while building

- There is no tool to create a level. `Asset.duplicate` of `/Engine/Maps/Templates/Template_Default`
  into `/Game` gives a lit level with a player start.
- `Scene.load_level` refuses while the open level has unsaved changes; save it first.
- `/Game/ThirdPerson/Blueprints` came from the C++ template. Its Blueprints have no parent class in this
  Blueprint-only project, and setting `defaultGameMode` to one fails with "not valid Class". The Guard
  pack's copies under `/Game/Guard/Demo/ThirdPerson/Blueprints` work.
- The template sun has a roll of 112. Changing only its pitch through `set_actor_transform` read back as
  the new pitch, but rendered the sun near the horizon (orange light, long shadows). Write the whole
  rotation with roll 0.
- `Scene.get_actors_in_folder` fails when the folder does not exist; check `Scene.get_folders` first.
- A prop can cover its tile centre, so floor traces skip tiles that hold a prop.
- `App.StopPIE` only requests the stop. A tool called before it lands fails with "The Editor is currently
  in a play mode". `uikit.PIE` now waits until `IsPIERunning` is false.
- One run crashed the editor with a Metal GPU hang in post-processing (`kIOGPUCommandBufferCallbackErrorHang`).
  Restart with `tools/restart_editor.sh` and run again; the next run passed.
