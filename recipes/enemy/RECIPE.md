# Enemy AI recipe

A mannequin enemy that patrols, sees a target through a line trace, chases it and attacks its
`BP_HealthComponent`. Its animation changes with its state, and a weapon mesh is attached to the right hand.
Built through Epic's Unreal MCP and verified in Play-in-Editor.

## Run it

```bash
python3 recipes/health/build/health.py --fresh   # once; the enemy damages BP_HealthComponent
python3 recipes/enemy/build/enemy.py --fresh
```

`--fresh` deletes the five enemy Blueprints, restarts the editor and rebuilds. The test places an
arena floor at Z=4000 in `/Game/MCPTest/L_OcclusionTest` with the enemy, a target and a wall on it,
drives four positions with keys in PIE and ends with `ENEMY PASS`. Everything is removed from the level
afterwards. `--verify-only` skips the build.

The character content is already in the project: `/Game/Characters/Mannequins` (mesh
`SKM_Manny_Simple`, skeleton with a `hand_r` socket, unarmed idle, jog and attack animations).
Nothing needs importing.

## What gets built

| Asset | Parent | Contents |
| --- | --- | --- |
| `/Game/Enemy/BP_Enemy` | `Character` | Instance-editable `Target` (Actor). Tuning: `SightRange` 1500, `AttackRange` 200, `AttackDamage` 10, `AttackInterval` 1 s. State: `State` (0 patrol, 1 chase, 2 attack), `CanSeeTarget`, `InAttackRange`, `CurrentAnim`. Patrol: `Home` (BeginPlay location), `PatrolOffset` (400, 0, 0), `PatrolSign`. Animations `IdleAnim`, `ChaseAnim`, `AttackAnim`. A `Weapon` static mesh component. Mesh `SKM_Manny_Simple`, walk speed 300, orient rotation to movement on, controller yaw off. |
| `/Game/Enemy/BP_EnemyTarget` | `Actor` | Box (BlockAll), cube mesh, `BP_HealthComponent` named `Health`. |
| `/Game/Enemy/BP_EnemyWall` | `Actor` | Box 40 x 600 x 400 (BlockAll), cube mesh. |
| `/Game/Enemy/BP_EnemyArena` | `Actor` | Floor box 3000 x 3000 x 20 (BlockAll), cube mesh. |
| `/Game/Enemy/BP_EnemyTest` | `Actor` | Instance-editable `Enemy`, `Target`, `Wall`. Keys below. |

### BP_Enemy functions

| Function | What it does |
| --- | --- |
| `Perceive` | `InAttackRange` = distance to `Target` within `AttackRange`. `CanSeeTarget` = within `SightRange` and a Visibility trace from 60 units above the enemy to the target hits an actor with `BP_HealthComponent`. A wall in between stops the trace on the wall, so the cast fails. |
| `DecideState` | `State` = 2 if it sees the target and is in range, 1 if it only sees it, else 0. |
| `ApplyAnim` | When `State` differs from `AnimState`, plays the state's animation looping (single-node mode) and stores it in `CurrentAnim`. |
| `Think` | Calls `Perceive`, `DecideState`, `ApplyAnim`. Tick calls it, and the test calls it right after moving actors, so results are readable in the same frame. |
| `Act` | Chase: movement input toward the target. Attack: `ApplyDamage(AttackDamage)` on the target's health component every `AttackInterval`, printing `ENEMY_ATTACK`. Patrol: walk between `Home` and `Home + PatrolOffset`, turning within 50 units. |

BeginPlay offsets the mesh (0, 0, -90) with yaw -90, sets single-node animation mode, attaches
`Weapon` to `hand_r` and prints `ENEMY_READY socket=<socket exists> at=<socket it landed on>`.

## Test sequence

Each key resets the enemy to (0, 0), moves the target and wall, calls `Think` and prints
`EN state= see= range= dist= hp= anim=`.

| Key | Target | Expected |
| --- | --- | --- |
| One | 3000 away | state 0, see false, `MM_Idle`; 2 s later the patrol has moved the enemy more than 100 units |
| Two | 800 away | state 1, see true, range false, `MF_Unarmed_Jog_Fwd`; 1 s later the distance has dropped more than 150 |
| Three | 150 away | state 2, range true, `MM_Attack_01`; 2.5 s later target hp is down at least 20 |
| Four | 800 away, wall at 400 | state 0, see false, `MM_Idle` |

Measured run: patrol 3000 to 2714, chase 800 to 114, attack hp 60 to 20.

## Traps found while building

- A Blueprint calling its own function uses `(CallFunction|<Name>)`, not `Class|BP<Name>|<Fn> :self self`,
  and the node exists only after the function's Blueprint is compiled. Compile before writing the caller.
- There is no `Utilities|Conversions|ToFloat(Integer)` node. Keep a value that is multiplied into a vector
  as a `real`.
- Name to string is `Utilities|String|ToString(Name)`.
- Object equality has no plain `==` node in the DSL (only `Asserts|AssertEqual(Object)` matches), so the
  sight check identifies the target by casting the hit actor to `BP_HealthComponent` instead of comparing actors.
- `Pawn|Input|AddMovementInput` takes a raw offset as `WorldDirection`; CharacterMovement clamps input to
  length 1 and ignores Z while walking, so no normalize node is needed. A Character placed in the level
  gets an AI controller by default, which the movement needs.
- The mesh offset is set in BeginPlay with `Transformation|SetRelativeLocationAndRotation`, because writing
  `relativeLocation` on a component template through `Object.set_properties` sets only X.
- Chase speed outruns the test harness: by the time the next key lands, the enemy may already be in attack
  range. The chase check accepts state 1 or 2 and measures the distance drop.
