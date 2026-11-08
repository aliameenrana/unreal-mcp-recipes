# Inventory recipe

A stack-limited inventory built from data assets, an Actor Component and a
world pickup. Built through Epic's Unreal MCP and verified in Play-in-Editor.

## Run it

```bash
python3 recipes/inventory/build/inventory.py --fresh
```

It deletes any earlier build, rebuilds every asset, places a test actor and a
coin pickup in `/Game/MCPTest/L_OcclusionTest`, drives them with keys in PIE
and ends with `INVENTORY PASS`. Both actors are removed from the level after the run.
`--verify-only` skips the build.

## What gets built

| Asset | Parent | Contents |
| --- | --- | --- |
| `/Game/Inventory/BP_ItemDefinition` | `PrimaryDataAsset` | `DisplayName` (string), `MaxStack` (int). |
| `/Game/Inventory/Items/DA_Potion`, `DA_Coin` | item definition | MaxStack 5 and 99. Add items by creating more data assets; no code changes. |
| `/Game/Inventory/BP_InventoryComponent` | `ActorComponent` | Parallel arrays `Items` (item refs) and `Counts` (int). `AddItem(Item, Count) -> Added` caps at MaxStack and returns what fit. `GetCount(Item) -> Count`. `RemoveItem(Item, Count) -> Removed`. Dispatcher `OnInventoryChanged` fires on every change. |
| `/Game/Inventory/BP_Pickup` | `Actor` | `Trigger` sphere plus a `Visual` sphere mesh (scale 0.4, NoCollision). Instance-editable `Item` and `Count`. On overlap it finds the other actor's inventory component, adds, prints `INV_PICKED` and destroys itself. |
| `/Game/Inventory/BP_InventoryTest` | `Actor` | Test driver; keys below. |

## Test sequence

| Key | Action | Expected print after `R` |
| --- | --- | --- |
| T | Add an inventory component to the pawn, teleport it onto the pickup (500, 0, 0) | `INV potion=0 coin=3` and `INV_PICKED` |
| A | Add 10 potions | `INV potion=5 coin=3` (stack cap 5) |
| X | Remove 1 coin | `INV potion=5 coin=2` |

## Traps found while building

- On `--fresh`, `Asset.delete` reports success but leaves an asset that another
  Blueprint or a placed actor still references, and the next `create` fails with
  "already exists". Unplace actors first, then delete dependents before the assets they
  use: test actor, pickup, component, data assets, item definition. Then check
  `Asset.exists` again.
- Data assets of a Blueprint class: `DataAsset.create` with `asset_type` set to the
  generated class (`..._C`). Compile the class before creating them.
- `Actor.set_actor_transform` on a placed Blueprint actor returns success and leaves
  it at the origin. Set `relativeLocation` on the actor's `RootComponent` with
  `Object.set_properties` and read it back. On this level the Z value read back as 0,
  so the test keeps the pickup and the teleport target at Z=0.
- `PrimitiveTools.add_sphere` rejects Blueprints. Add a `StaticMeshComponent` and set
  `staticMesh`, `relativeScale3D` and `bodyInstance.collisionProfileName` on it.
- `set_variable_instance_editable` takes `variable_name`, not `name`.
- A pure node bound with `bind` is evaluated again at every use. Store values that must
  not change (here, the amount added) in a member variable before writing arrays.
- The PIE driver releases Slate observers after every snapshot and before StopPIE.
  Observers left open make StopPIE assert `GameViewport.IsUnique()` and crash the editor.
