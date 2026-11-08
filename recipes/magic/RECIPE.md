# Magic recipe

Spells as data assets, a caster component with mana, regen and per-spell cooldowns, and a
projectile that damages anything carrying `BP_HealthComponent`. Built through Epic's Unreal
MCP and verified in Play-in-Editor.

## Run it

```bash
python3 recipes/health/build/health.py --fresh   # once; magic uses BP_HealthComponent
python3 recipes/magic/build/magic.py --fresh
```

The script deletes any earlier build and rebuilds every asset. It then places a caster and a
target dummy 600 units apart in `/Game/MCPTest/L_OcclusionTest` and drives them with keys in PIE.
The last line is `MAGIC PASS`. Both actors are removed from the level after the run.
`--verify-only` skips the build.

## What gets built

| Asset | Parent | Contents |
| --- | --- | --- |
| `/Game/Magic/BP_SpellDefinition` | `PrimaryDataAsset` | `DisplayName` (string), `ManaCost`, `Cooldown`, `Damage` (real). |
| `/Game/Magic/Spells/DA_Fireball` | spell definition | Cost 30, cooldown 2 s, damage 25. |
| `/Game/Magic/Spells/DA_Frostbolt` | spell definition | Cost 10, cooldown 0.5 s, damage 10. New spells are new data assets. |
| `/Game/Magic/BP_SpellCaster` | `ActorComponent` | `MaxMana` 100, `Mana`, `ManaRegen` 10/s applied on Tick. Parallel arrays `Spells` and `ReadyAt` (game time). `TryCast(Spell) -> Result` returns 0 cast, 1 on cooldown, 2 not enough mana. On 0 it spends mana, sets the cooldown and spawns the projectile 100 units in front of the owner along its forward vector. Dispatcher `OnManaChanged`. |
| `/Game/Magic/BP_SpellProjectile` | `Actor` | `Collision` sphere (radius 16), `Visual` sphere mesh, `Movement` ProjectileMovement (speed 1500, gravity 0), `Damage`. Life span 3 s. On overlap with an actor that has `BP_HealthComponent` it calls `ApplyDamage(Damage)`, prints `MAG_HIT` and destroys itself. Actors without health are passed through. |
| `/Game/Magic/BP_MagicTarget` | `Actor` | `Hitbox` box (50x50x100), cylinder mesh, `BP_HealthComponent` named `Health`. |
| `/Game/Magic/BP_MagicTest` | `Actor` | Owns a `BP_SpellCaster`; instance-editable `Target`. Keys below. |

## Test sequence

| Step | Expected |
| --- | --- |
| F (Fireball) | `MAG_CAST 0 mana=70`; projectile hits, target hp 100 -> 75 |
| F again within the cooldown | `MAG_CAST 1` |
| M: set mana to 5 and cast Frostbolt in the same frame | `MAG_CAST 2 mana=5` |
| Wait 2 s, R twice | mana rises (about 16 -> 48) |
| G (Frostbolt) | `MAG_CAST 0`; hit; target hp 75 -> 65 |

## Traps found while building

- There is no tool to set a Blueprint variable's default. Compile, get the class default object
  with `BP.get_default_object`, then `Object.set_properties` on it and read it back.
- `Utilities|Time|GetGameTimeinSeconds` has no input pins in a Blueprint graph; call it bare.
- A component's owner is `Components|GetOwner`, not `Class|ActorComponent|GetOwner`.
- Setting a variable on another Blueprint's instance: `(Class|BP<Name>|Set<Var> :self obj :<Var> v)`,
  where `<Name>` is the asset name without underscores (`BP_SpellProjectile` -> `BPSpellProjectile`).
- Add a Blueprint component to an actor Blueprint with `Actor.add_component` and the component's
  generated class (`.../BP_HealthComponent.BP_HealthComponent_C`).
- Regen keeps running between key presses, and a background editor's game time runs slower than
  wall-clock time. Read mana in the same frame as the action you test, by printing it alongside the
  cast result. For the mana-rejection case, drain and cast in one key handler.
