#!/usr/bin/env python3
"""Builds and PIE-verifies the vehicles recipe: a Chaos wheeled sports car with front and rear wheel
classes, engine torque curve, chase camera, WASD driving, and a flat test track.

  python3 recipes/vehicles/build/vehicles.py [--fresh] [--verify-only]

Needs the ChaosVehiclesPlugin enabled and the vehicle content imported (see RECIPE.md).
"""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../tools"))
import mcp
from uikit import must, ref, save, place, unplace, fresh_wipe, PIE, Fail
from bpkit import collision, create, ensure_bp, var, obj_var, defaults, component, key, compile_bp, set_props

F = "/Game/VehicleRecipe"
CAR = f"{F}/BP_Car.BP_Car"
FW = f"{F}/BP_FrontWheel.BP_FrontWheel"
RW = f"{F}/BP_RearWheel.BP_RearWheel"
TRACK = f"{F}/BP_TestTrack.BP_TestTrack"
T = f"{F}/BP_VehicleTest.BP_VehicleTest"
MESH = "/Game/Vehicles/SportsCar/SKM_SportsCar.SKM_SportsCar"
ANIM = "/Game/Vehicles/SportsCar/ABP_SportsCar.ABP_SportsCar_C"
TORQUE = "/Game/VehicleTemplate/Blueprints/SportsCar/FC_Torque_SportsCar.FC_Torque_SportsCar"
LEVEL = "/Game/MCPTest/L_OcclusionTest"
TRACK_Z = 3000
# Values from the UE 5.8 vehicle template (SportsCar_WheelsFront / SportsCar_WheelsRear).
WHEEL = {"wheelMass": 20.0, "maxHandBrakeTorque": 6000.0, "suspensionMaxRaise": 10.0, "suspensionMaxDrop": 10.0,
         "springRate": 250.0, "springPreload": 50.0, "suspensionDampingRatio": 0.5, "wheelLoadRatio": 0.5,
         "corneringStiffness": 1000.0, "sideSlipModifier": 1.0}
FRONT = dict(WHEEL, wheelRadius=39.0, wheelWidth=35.0, maxSteerAngle=40.0, bAffectedBySteering=True,
             bAffectedByHandbrake=False, bAffectedByEngine=False, bAffectedByBrake=True, maxBrakeTorque=4500.0,
             frictionForceMultiplier=3.0, slipThreshold=20.0, skidThreshold=20.0, axleType="Front")
REAR = dict(WHEEL, wheelRadius=40.0, wheelWidth=40.0, maxSteerAngle=0.0, bAffectedBySteering=False,
            bAffectedByHandbrake=True, bAffectedByEngine=True, bAffectedByBrake=True, maxBrakeTorque=1500.0,
            frictionForceMultiplier=4.0, slipThreshold=100.0, skidThreshold=100.0, axleType="Rear")
V = lambda n: f"(Variables|Default|Get{n})"


def wipe():
    fresh_wipe(LEVEL, [T, CAR, TRACK], [T, TRACK, CAR, FW, RW])


def build_wheels():
    for path, vals in ((FW, FRONT), (RW, REAR)):
        create(path, "/Script/ChaosVehicles.ChaosVehicleWheel")
        defaults(path, vals)


def build_car():
    """WASD drives when held. Otherwise AutoThrottle/AutoSteer/AutoBrake drive it (set by the test)."""
    create(CAR, "/Script/ChaosVehicles.WheeledVehiclePawn")
    for n in ("AutoThrottle", "AutoSteer", "AutoBrake"):
        var(CAR, n, "real")
    compile_bp(CAR)
    cdo = must("BP", "get_default_object", {"blueprint": ref(CAR)})
    comps = json.loads(must("Object", "get_properties", {"instance": cdo, "properties": ["Mesh", "VehicleMovementComponent"]}))
    set_props(comps["Mesh"], {"skeletalMesh": MESH, "animClass": ANIM}, "VehicleMesh")
    # WheeledVehiclePawn's mesh does not simulate by default; without this the car hangs in the air.
    must("Object", "set_properties", {"instance": comps["Mesh"], "values": json.dumps({"bodyInstance": {"bSimulatePhysics": True}})})
    body = json.loads(must("Object", "get_properties", {"instance": comps["Mesh"], "properties": ["bodyInstance"]}))["bodyInstance"]
    if not body["bSimulatePhysics"] or body["collisionProfileName"] != "Vehicle":
        raise Fail(f"VehicleMesh physics: simulate={body['bSimulatePhysics']} profile={body['collisionProfileName']}")
    wheels = [{"wheelClass": f"{c}_C", "boneName": b} for c, b in
              ((FW, "Phys_Wheel_FL"), (FW, "Phys_Wheel_FR"), (RW, "Phys_Wheel_BL"), (RW, "Phys_Wheel_BR"))]
    move = comps["VehicleMovementComponent"]
    must("Object", "set_properties", {"instance": move, "values": json.dumps({
        "wheelSetups": wheels, "bRequiresControllerForInputs": False,
        "engineSetup": {"torqueCurve": {"externalCurve": TORQUE}, "maxTorque": 750.0, "maxRPM": 7000.0}})})
    got = json.loads(must("Object", "get_properties", {"instance": move, "properties": ["wheelSetups", "engineSetup",
                                                                                        "bRequiresControllerForInputs"]}))
    bones = [w["boneName"] for w in got["wheelSetups"]]
    if bones != [w["boneName"] for w in wheels] or "FC_Torque" not in json.dumps(got["engineSetup"]) \
            or got["engineSetup"]["maxTorque"] != 750 or got["bRequiresControllerForInputs"]:
        raise Fail(f"movement setup did not stick: {json.dumps(got)[:400]}")
    arm = component(CAR, "/Script/Engine.SpringArmComponent", "SpringArm",
                    {"targetArmLength": 650.0, "relativeLocation": {"x": 0.0, "y": 0.0, "z": 150.0}})
    set_props(arm, {"relativeRotation": {"pitch": -15.0, "yaw": 0.0, "roll": 0.0}}, "SpringArm")
    component(CAR, "/Script/Engine.CameraComponent", "Camera")
    pc = "(Game|GetPlayerController 0)"
    down = lambda k: f'(Game|Player|IsInputKeyDown :self {pc} :Key "{k}")'
    axis = lambda neg, pos: f"(- (select {down(pos)} 1.0 0.0) (select {down(neg)} 1.0 0.0))"
    manual = f'(or (or {down("W")} {down("S")}) (or {down("A")} {down("D")}))'
    move_node = "(Variables|Vehicle|GetVehicleMovementComponent)"
    must("BP", "write_graph_dsl", {"graph": CAR + ":EventGraph", "code": f"""
(event AddEvent|EventTick (DeltaSeconds)
  (bind mc {move_node})
  (if {manual}
    (Game|Components|ChaosVehicleMovement|SetThrottleInput :self mc :Throttle (select {down("W")} 1.0 0.0))
    (Game|Components|ChaosVehicleMovement|SetBrakeInput :self mc :Brake (select {down("S")} 1.0 0.0))
    (Game|Components|ChaosVehicleMovement|SetSteeringInput :self mc :Steering {axis("A", "D")})
    (else
      (Game|Components|ChaosVehicleMovement|SetThrottleInput :self mc :Throttle {V('AutoThrottle')})
      ; Auto-reverse turns a held brake into reverse throttle once the car stops: release the brake
      ; below ~1 km/h (28 cm/s) and hold the car with the handbrake instead.
      (bind moving (> (Math|Float|Absolute(Float) (Game|Components|ChaosVehicleMovement|GetForwardSpeed :self mc)) 28.0))
      (Game|Components|ChaosVehicleMovement|SetBrakeInput :self mc :Brake (select moving {V('AutoBrake')} 0.0))
      (Game|Components|ChaosVehicleMovement|SetHandbrakeInput :self mc
        :bNewHandbrake (and (> {V('AutoBrake')} 0.0) (not moving)))
      (Game|Components|ChaosVehicleMovement|SetSteeringInput :self mc :Steering {V('AutoSteer')}))))"""})
    compile_bp(CAR)


def build_track():
    create(TRACK, "/Script/Engine.Actor")
    component(TRACK, "/Script/Engine.StaticMeshComponent", "Floor", {
        "staticMesh": "/Engine/BasicShapes/Cube.Cube", "relativeScale3D": {"x": 1000.0, "y": 1000.0, "z": 1.0},
        "bodyInstance": collision("BlockAll")})
    compile_bp(TRACK)


def build_test():
    """1: full throttle. 2: steer right with throttle. 3: release throttle, full brake. R: print state."""
    create(T, "/Script/Engine.Actor")
    obj_var(T, "Car", CAR + "_C", editable=True)
    car = "(Variables|Default|GetCar)"
    setv = lambda t, s, b: f"""
    (Class|BPCar|SetAutoThrottle :self {car} :AutoThrottle {t})
    (Class|BPCar|SetAutoSteer :self {car} :AutoSteer {s})
    (Class|BPCar|SetAutoBrake :self {car} :AutoBrake {b})"""
    mc = f"(Class|WheeledVehiclePawn|GetVehicleMovementComponent :self {car})"
    num = lambda x: f"(Utilities|String|ToString(Float) {x})"
    report = f"""
    (bind loc (Transformation|GetActorLocation :self {car}))
    (bind rot (Transformation|GetActorRotation :self {car}))
    (Development|PrintString (Utilities|String|Append "VEH speed="
      (Utilities|String|Append {num(f"(* (Game|Components|ChaosVehicleMovement|GetForwardSpeed :self {mc}) 0.036)")}
      (Utilities|String|Append " x=" (Utilities|String|Append {num("(.x loc)")}
      (Utilities|String|Append " y=" (Utilities|String|Append {num("(.y loc)")}
      (Utilities|String|Append " z=" (Utilities|String|Append {num("(.z loc)")}
      (Utilities|String|Append " yaw=" (Utilities|String|Append {num("(.yaw rot)")}
      (Utilities|String|Append " gear=" (Utilities|String|ToString(Integer)
        (Game|Components|ChaosVehicleMovement|GetCurrentGear :self {mc}))))))))))))))"""
    code = '(event AddEvent|EventBeginPlay (Development|PrintString "VEH_READY"))\n(event AddEvent|EventTick (DeltaSeconds)'
    code += key("One", setv(1.0, 0.0, 0.0)) + key("Two", setv(1.0, 1.0, 0.0)) + key("Three", setv(0.0, 0.0, 1.0))
    code += key("R", report) + ")"
    must("BP", "write_graph_dsl", {"graph": T + ":EventGraph", "code": code})
    compile_bp(T)


def verify():
    place(LEVEL, TRACK, "TestTrack", (0, 0, TRACK_Z))
    car = place(LEVEL, CAR, "Car", (0, 0, TRACK_Z + 150))
    test = place(LEVEL, T, "VehicleTest", (0, 0, TRACK_Z + 500))
    set_props(test, {"Car": car["refPath"]}, "VehicleTest")
    try:
        with PIE() as p:
            time.sleep(3)
            assert "VEH_READY" in p.markers("VEH_READY"), "test actor did not start"

            def state(first=False):
                got = p.press_expect("R", "VEH speed=")
                line = "speed=" + got.rsplit("VEH speed=", 1)[1].split('"')[0]
                return {k: float(v) for k, v in (kv.split("=") for kv in line.split())}

            s0 = state(True)
            print("  rest:", s0)
            assert abs(s0["speed"]) < 2 and s0["z"] > TRACK_Z, f"car not resting on the track: {s0}"
            p.key("One", focus_game=False)
            time.sleep(2.5)
            s1 = state()
            print("  throttle:", s1)
            assert s1["speed"] > 20 and s1["x"] - s0["x"] > 500, f"car did not accelerate forward: {s1}"
            assert s1["z"] > TRACK_Z, f"car fell through the track: {s1}"
            p.key("Two", focus_game=False)
            time.sleep(2)
            s2 = state()
            print("  steer right:", s2)
            assert s2["z"] > TRACK_Z, f"car left the track: {s2}"
            assert s2["yaw"] - s1["yaw"] > 15, f"car did not turn right: {s1['yaw']} -> {s2['yaw']}"
            p.key("Three", focus_game=False)
            time.sleep(5)
            s3 = state()
            print("  brake:", s3)
            assert abs(s3["speed"]) < 3, f"car did not stop: {s3}"
    finally:
        for a in (T, CAR, TRACK):
            unplace(LEVEL, a)
        save([LEVEL])
    print("VEHICLES PASS")


if __name__ == "__main__":
    mcp.init()
    for a in (MESH, ANIM.rsplit("_C", 1)[0], TORQUE):
        if not must("Asset", "exists", {"path": a}):
            raise Fail(f"missing {a}: import the vehicle content first (RECIPE.md)")
    if "--verify-only" not in sys.argv:
        if "--fresh" in sys.argv:
            wipe()
        build_wheels()
        build_car()
        build_track()
        build_test()
        save([x.split(".")[0] for x in (FW, RW, CAR, TRACK, T)])
    verify()
