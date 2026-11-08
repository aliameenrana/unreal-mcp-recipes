# Health and scoring recipe

Two reusable Actor Components, built through Epic's Unreal MCP and verified in
Play-in-Editor. Attach them to any actor (player, enemy, destructible prop).

## Run it

```bash
python3 recipes/health/build/health.py --fresh
```

It builds both components and a test actor, places the actor in
`/Game/MCPTest/L_OcclusionTest`, drives it with keys in PIE, prints each state
and ends with `HEALTH PASS`. The test actor is removed from the level afterwards.

## What gets built

`/Game/Gameplay/BP_HealthComponent` (parent `ActorComponent`)

| Member | Kind | Behavior |
| --- | --- | --- |
| `MaxHealth` | real, default 100 | Set per actor on the component's details. |
| `Health` | real | Set to `MaxHealth` on BeginPlay. |
| `bDead` | bool | True once Health reaches 0. |
| `ApplyDamage(Amount)` | function | Clamps to 0..Max, fires `OnHealthChanged`; at 0 sets `bDead`, stops any DoT, fires `OnDeath`. Ignored when dead. |
| `Heal(Amount)` | function | Clamps to Max, fires `OnHealthChanged`. Ignored when dead. |
| `ApplyDamageOverTime(PerSecond, Duration)` | function | Debuff timer on component Tick; replaces any running DoT. |
| `OnHealthChanged`, `OnDeath` | event dispatchers | No parameters; listeners read `Health` from the component. |

`/Game/Gameplay/BP_ScoreComponent`: `Score` (int), `AddScore(Points)`,
dispatcher `OnScoreChanged`.

## Verified in PIE

| Input | Expected | Result |
| --- | --- | --- |
| start | hp 100, alive, score 0 | pass |
| damage 30 | hp 70 | pass |
| heal 10 | hp 80 | pass |
| DoT 25/s for 2 s | hp 30 | pass |
| score +10 | score 10 | pass |
| damage 30 at hp 30 | hp 0, dead | pass |
| heal 10 while dead | hp stays 0 | pass |

## Steps, in order

1. `BP.create {folder_path, asset_name, asset_type: {"refPath": "/Script/Engine.ActorComponent"}}`.
2. `BP.add_variable` per member (`real`, `bool`, `int`).
3. `BP.add_event_dispatcher {blueprint, name}`. Fire it with `(Default|CallOnDeath)`.
4. Per function: `BP.add_function_graph {blueprint, graph_name}` returns the
   graph ref; `BP.add_function_param {graph, param_name, param_type, input_param: true, container_type: null}`
   per input; then `BP.write_graph_dsl {graph: "<BP>:<Function>", code: "(fn Name (Params) ...)"}`.
5. `BP.compile_blueprint {blueprint}`.
6. Defaults: `Object.set_properties` on `<path>.Default__<Name>_C` with
   `values: "{\"MaxHealth\": 100.0}"`, then `get_properties` to confirm.
7. Attach to an actor Blueprint: `Actor.add_component {owner: <actor BP>, component_type: "<path>_C", name: "HealthComp"}`
   (toolset `editor_toolset.toolsets.actor.ActorTools`).
8. Call from the owner: `(Class|BPHealthComponent|ApplyDamage :self (Variables|Default|GetHealthComp) :Amount 30.0)`.
   Getters: `Class|BPHealthComponent|GetHealth`, `GetDead`.

## Traps

- **Bool names drop the `b` prefix in node IDs.** Variable `bDead` is
  `Variables|Default|GetDead` / `SetDead`, and `Class|BPHealthComponent|GetDead`
  from outside.
- **`bind` on a pure node is not a snapshot.** Every reader re-runs the getter.
  If you `Set` a variable and later read a value derived from its earlier `bind`,
  you get the new value. The DoT first lost 1.2 of its 50 damage this way. Do
  the work that needs the old value before the `Set`.
- **Same-graph function calls need keyword arguments.** `(CallFunction|ApplyDamage x)`
  wires `x` into `self` and fails; write `(CallFunction|ApplyDamage :Amount x)`.
- **`find_actors` takes Actor classes only.** Passing a component class throws;
  don't try to unplace components.
- **Game time is behind wall-clock while the editor is in the background.**
  Timed checks wait longer than the effect's duration (8 s for a 2 s DoT) and
  compare floats with a tolerance.

## Wiring into the HUD

After creating `WBP_HUD` (UI recipe), on `OnHealthChanged` set
`Class|WBPHUD|SetHealth` to `Health / MaxHealth`, and on `OnScoreChanged` set
`Class|WBPHUD|SetScore`. On `OnDeath`, open `WBP_GameOver` with
`uikit.open_menu_dsl`.

## Out of scope

Engine `ApplyDamage`/`OnTakeAnyDamage` routing (binding owner delegates from the
DSL is untested), replication, damage types and armor.
