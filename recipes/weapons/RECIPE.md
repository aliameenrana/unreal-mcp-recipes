# Weapons recipe

Hitscan weapons as data assets and a weapon component with a magazine, a fire interval and a
timed reload. Hits apply damage to anything carrying `BP_HealthComponent`. Built through Epic's
Unreal MCP and verified in Play-in-Editor.

## Run it

```bash
python3 recipes/health/build/health.py --fresh   # once; weapons use BP_HealthComponent
python3 recipes/weapons/build/weapons.py --fresh
```

`--fresh` deletes the logic Blueprints (test actor, target, weapon component), restarts the editor
and rebuilds. The weapon definition class and the weapon data assets are kept and their values
rewritten. The test places a shooter and a target 600 units apart at Z=2000 in
`/Game/MCPTest/L_OcclusionTest`, drives them with keys in PIE and ends with `WEAPONS PASS`.
`--verify-only` skips the build.

## What gets built

| Asset | Parent | Contents |
| --- | --- | --- |
| `/Game/Weapons/BP_WeaponDefinition` | `PrimaryDataAsset` | `DisplayName`, `Damage`, `Range`, `FireInterval`, `ReloadTime` (real), `MagazineSize` (int). |
| `/Game/Weapons/Data/DA_Pistol` | weapon definition | Damage 10, range 5000, interval 0.25 s, magazine 6, reload 1.5 s. |
| `/Game/Weapons/Data/DA_Rifle` | weapon definition | Damage 25, range 10000, interval 0.1 s, magazine 30, reload 2.5 s. |
| `/Game/Weapons/BP_WeaponComponent` | `ActorComponent` | Instance-editable `Weapon` (default DA_Pistol), `Ammo`, `NextFireAt`, `ReloadEndsAt`, `LastHit`. BeginPlay fills the magazine. `Fire() -> Result`: 0 fired, 1 interval not elapsed, 2 empty, 3 reloading. A shot traces Visibility from 50 units in front of the owner along its forward vector for `Range`, draws the debug line for 1 s, prints `WPN_DBG hit <actor>` or `WPN_DBG miss`, and calls `ApplyDamage` on the hit actor's health component. `Reload() -> Started` starts a timed reload; Tick refills the magazine when it ends. Dispatchers `OnFired`, `OnReloaded`. |
| `/Game/Weapons/BP_ShootingTarget` | `Actor` | `Hitbox` box (BlockAll), cube mesh, `BP_HealthComponent` named `Health`. |
| `/Game/Weapons/BP_WeaponTest` | `Actor` | Owns a `BP_WeaponComponent`; instance-editable `Target`. Keys below. |

## Test sequence

| Key | Action | Expected `WPN_FIRE` |
| --- | --- | --- |
| F | Fire | `0 ammo=5 hit=true` |
| D | Fire twice in one frame | second shot `1 ammo=4` (interval); target hp 80 |
| Z | Empty the magazine and fire | `2 ammo=0` |
| Q | Start a reload and fire in the same frame | `3 ammo=0` |
| wait 3 s, F | Magazine refilled to 6, fire | `0 ammo=5 hit=true`; target hp 70 |

## Traps found while building

- Setting `bodyInstance.collisionProfileName` on a component template only renames the profile:
  the per-channel responses keep their old values (a box stays Overlap on Visibility), so traces pass
  through. `bpkit.collision("BlockAll" | "OverlapAll" | "NoCollision")` writes the name, the enabled
  state, the object type and every channel response.
- Deleting a class whose default object references a data asset leaves that data asset loaded after
  its file is gone. `Asset.exists` stays True and `create` fails. Rebuilding Blueprints in the same
  session that deleted them crashed the editor once (SIGSEGV in `UStruct::SerializeExpr`).
  `uikit.fresh_wipe` deletes and then restarts the editor; data definitions are kept (`bpkit.ensure_bp`,
  `bpkit.data_assets` create only what is missing).
- `Collision|LineTraceByChannel` returns `(OutHit ReturnValue)`; bind both, then bind all 18 outputs of
  `Collision|BreakHitResult` positionally to reach `HitActor` (the 10th). The Visibility channel is
  `"TraceTypeQuery1"`.
- A cast is a multi-exec node and ends the exec flow, so a `return` after it is never wired. Put the
  `return` inside every continuation.
- L_OcclusionTest has occluder meshes near the ground. The trace hit a `StaticMeshActor` until the lane
  moved to Z=2000.
- Fire rate and reload state checks run in one key handler (fire twice, or reload then fire), so the
  result does not depend on how long the test harness takes between presses.
