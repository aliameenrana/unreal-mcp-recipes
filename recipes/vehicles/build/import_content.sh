#!/bin/zsh
# Import the UE 5.8 vehicle template content and enable ChaosVehiclesPlugin, then restart the editor.
# The sports car comes from the template's shared "Vehicles" pack, which mounts at /Game/Vehicles;
# the wheel classes and torque curve the recipe reads values from live in /Game/VehicleTemplate.
set -eu
ENGINE_DIR="/Users/Shared/Epic Games/UE_5.8"
ROOT="${0:A:h}/../../.."
PROJ="$ROOT/UnrealProject"
SRC="$ENGINE_DIR/Templates/TemplateResources/Standard/Vehicles/Content"
TPL="$ENGINE_DIR/Templates/TP_VehicleAdvBP/Content/VehicleTemplate/Blueprints/SportsCar"

mkdir -p "$PROJ/Content/Vehicles" "$PROJ/Content/VehicleTemplate/Blueprints/SportsCar"
rsync -a --exclude '*.FBX' --exclude '*.fbx' "$SRC/SportsCar" "$SRC/PhysicsMaterials" "$PROJ/Content/Vehicles/"
cp "$TPL"/SportsCar_WheelsFront.uasset "$TPL"/SportsCar_WheelsRear.uasset "$TPL"/FC_Torque_SportsCar.uasset \
   "$PROJ/Content/VehicleTemplate/Blueprints/SportsCar/"

python3 - "$PROJ/SequencesTestProject.uproject" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
plugins = d.setdefault("Plugins", [])
if not any(x["Name"] == "ChaosVehiclesPlugin" for x in plugins):
    plugins.append({"Name": "ChaosVehiclesPlugin", "Enabled": True})
    json.dump(d, open(p, "w"), indent="\t")
    print("enabled ChaosVehiclesPlugin")
PY
"$ROOT/tools/restart_editor.sh"
