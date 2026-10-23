# Unreal MCP recipes

Step-by-step recipes that tell an AI coding agent how to build things in
Unreal Engine 5.8 through Epic's own MCP server (the experimental
`ModelContextProtocol` plugin that ships with 5.8).

Epic's server gives an agent the tools: create a Widget Blueprint, set a
property, write Blueprint graph logic, start Play-in-Editor. It does not say
which calls to make, in what order, with which argument formats, or which ones
fail without an error. Each recipe here records that, using tool calls and
formats tested against a running editor.

## Contents

| Path | What it is |
| --- | --- |
| [recipes/ui/RECIPE.md](recipes/ui/RECIPE.md) | UMG menus: theme, layout, styling, button handlers, tween animation, show/hide, verification in PIE. First target is a pause menu. |
| [recipes/ui/PROBES.md](recipes/ui/PROBES.md) | The live-editor tests behind the UI recipe and their results. |
| [recipes/ui/theme.example.json](recipes/ui/theme.example.json) | Example theme the styling sequence reads. |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Project brief: goals, format of sequences and recipes, the recipe catalog, known engine behavior and working rules. |
| [.mcp.json](.mcp.json) | Points an MCP client (Claude Code and others) at the editor's server on `localhost:8000/mcp`. |

## Terms

- **Sequence:** a short, ordered set of tool calls that does one job and ends
  with a check, for example `seq_style_widget` or `seq_verify_widget`.
- **Recipe:** sequences chained to build a feature, for example a pause menu.

## Setup

1. Unreal Engine 5.8 with a project that enables `ModelContextProtocol`,
   `ToolsetRegistry`, `EditorToolset`, `UMGToolSet`, `SlateInspectorToolset`
   and `PythonScriptPlugin`.
2. Turn the server on in `Config/DefaultEditorPerProjectUserSettings.ini`:

   ```ini
   [/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
   bAutoStartServer=True
   ServerPortNumber=8000
   ServerUrlPath=/mcp
   bEnableToolSearch=True
   ```

3. Open the project in the editor, then start your agent in this folder so it
   picks up `.mcp.json`.
4. Have the agent read the recipe before it builds.

## Status

| Recipe | State |
| --- | --- |
| UI (UMG) | Tool routes tested live; pause menu not built end to end yet. Items not yet run are marked in the recipe. |
| Enemy AI, inventory, weapons, magic, health, vehicles, level generation | Planned; see the catalog in `docs/HANDOFF.md`. |

Tested on UE 5.8, macOS. Epic's MCP plugin is experimental, so tool names and
formats may change between engine versions.
