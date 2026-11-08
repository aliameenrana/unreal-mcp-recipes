# Vehicles recipe

A drivable Chaos wheeled sports car: front and rear wheel classes, the template torque curve, a
chase camera, WASD driving, and an autopilot the test drives through. Built through Epic's Unreal
MCP and verified in Play-in-Editor on a flat 1 km test track.

## Run it

```bash
recipes/vehicles/build/import_content.sh        # once: copies template content, enables the plugin, restarts
python3 recipes/vehicles/build/vehicles.py --fresh
```

`import_content.sh` copies the sports car (skeletal mesh, physics asset, animation Blueprint,
materials) from the engine's vehicle template into `/Game/Vehicles`. It copies the template's wheel
classes and torque curve into `/Game/VehicleTemplate/Blueprints/SportsCar`. It adds
`ChaosVehiclesPlugin` to the `.uproject` and restarts the editor. The project folder is git-ignored,
so run it on every fresh checkout.

`--fresh` deletes the recipe Blueprints, restarts the editor and rebuilds. The test places a track
at Z=3000, the car on it and a test actor, then drives in PIE and ends with `VEHICLES PASS`.
`--verify-only` skips the build.

## What gets built

| Asset | Parent | Contents |
| --- | --- | --- |
| `/Game/VehicleRecipe/BP_FrontWheel` | `ChaosVehicleWheel` | Radius 39, width 35, steer 40°, brake 4500, friction 3, axle Front, no engine. Values from the template's `SportsCar_WheelsFront`. |
| `/Game/VehicleRecipe/BP_RearWheel` | `ChaosVehicleWheel` | Radius 40, width 40, no steering, engine and handbrake, brake 1500, friction 4, axle Rear. |
| `/Game/VehicleRecipe/BP_Car` | `WheeledVehiclePawn` | `VehicleMesh`: `SKM_SportsCar`, `ABP_SportsCar`, simulate physics. `VehicleMovementComp`: wheels FL/FR front and BL/BR rear on bones `Phys_Wheel_*`, torque curve `FC_Torque_SportsCar`, max torque 750, max RPM 7000, inputs without a controller. `SpringArm` (650, pitch -15) with `Camera`. Tick: held W/S/A/D drive it; otherwise `AutoThrottle`, `AutoSteer`, `AutoBrake` do. The auto brake stops the car and holds it with the handbrake. |
| `/Game/VehicleRecipe/BP_TestTrack` | `Actor` | Cube floor scaled 1000x1000x1 (1 km square), BlockAll. |
| `/Game/VehicleRecipe/BP_VehicleTest` | `Actor` | Instance-editable `Car`. Keys 1 throttle, 2 throttle + steer right, 3 brake, R print state. |

## Test sequence (one measured run)

| Step | Result |
| --- | --- |
| Rest | speed 0, z 3067 (settled on the track at 3050) |
| 1, 2.5 s | 96 km/h, x +5532, gear 2 |
| 2, 2 s | 140 km/h, yaw 0° -> 62°, still on the track |
| 3, 5 s | speed 0, held |

Assertions: speed above 20 km/h and 500 units forward after throttle; yaw up at least 15° after
steering; below 3 km/h after braking; the car stays above the track the whole time.

## Traps found while building

- Template Blueprints reference the shared pack at `/Game/Vehicles`. Copy it to that exact path or the
  references break.
- `WheeledVehiclePawn`'s `VehicleMesh` has `bSimulatePhysics` false on a new Blueprint. The car hangs in
  the air at its spawn height with speed 0. Set `bodyInstance.bSimulatePhysics` true and read it back.
- The default engine torque curve has no keys, so set `engineSetup.torqueCurve.externalCurve`.
  `wheelSetups` (array of structs) and `engineSetup` write and read back completely with
  `Object.set_properties` on the component template from `BP.get_default_object`.
- The movement component waits for a controller by default. Set `bRequiresControllerForInputs` false to
  drive an unpossessed car.
- `bUseAutoReverse` turns a held brake into reverse once the car stops (it reversed at 88 km/h). The
  autopilot releases the brake below 28 cm/s and sets the handbrake.
- From another Blueprint, the movement component getter is `Class|WheeledVehiclePawn|GetVehicleMovementComponent`.
  Inside the car it is `Variables|Vehicle|GetVehicleMovementComponent`. Driving nodes live under
  `Game|Components|ChaosVehicleMovement|`. `GetForwardSpeed` is cm/s (x 0.036 for km/h).
- At full throttle the car leaves a 400 m track in under 6 s. The 1 km track and the 2.5 s + 2 s phases
  keep it on.
- The first key press after StartPIE is sometimes dropped. `PIE.press_expect` retries until the expected
  log line appears.
