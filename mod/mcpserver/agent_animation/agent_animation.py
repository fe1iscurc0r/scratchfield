"""agent_animation - AI_Animation diagram & animation generator.

Generates architecture, workflow, sequence, dataflow, and lifecycle diagrams
using graphviz (primary) and matplotlib (fallback for animations/GIFs).

Tools:
  - generate_diagram:  Create a diagram from type + spec JSON
  - export_diagram:    Export to PNG/JPEG/SVG/GIF/WebM
  - list_templates:    List available diagram templates
"""

import base64
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Dependency checks with graceful fallback ────────────────────────────

_GRAPHVIZ_AVAILABLE = False
_MATPLOTLIB_AVAILABLE = False
_graphviz_import_error = None
_matplotlib_import_error = None

def _try_imports():
    global _GRAPHVIZ_AVAILABLE, _MATPLOTLIB_AVAILABLE
    global _graphviz_import_error, _matplotlib_import_error

    try:
        import graphviz  # noqa: F401
        _GRAPHVIZ_AVAILABLE = True
    except ImportError as e:
        _graphviz_import_error = str(e)

    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")  # non-interactive backend
        _MATPLOTLIB_AVAILABLE = True
    except ImportError as e:
        _matplotlib_import_error = str(e)

_try_imports()

# ── Diagram store ───────────────────────────────────────────────────────

_diagram_store: dict[str, dict] = {}

# ── Templates ───────────────────────────────────────────────────────────

TEMPLATES = {
    "architecture": {
        "name": "Architecture Diagram",
        "description": "High-level system architecture with components and connections",
        "spec_keys": ["components", "connections", "layers"],
        "example": {
            "components": [
                {"id": "web", "label": "Web Server", "layer": "frontend"},
                {"id": "api", "label": "API Gateway", "layer": "gateway"},
                {"id": "db", "label": "Database", "layer": "data"},
            ],
            "connections": [
                {"from": "web", "to": "api", "label": "HTTP"},
                {"from": "api", "to": "db", "label": "SQL"},
            ],
        },
    },
    "workflow": {
        "name": "Workflow Diagram",
        "description": "Step-by-step process flow with decision nodes",
        "spec_keys": ["steps", "decisions", "loops"],
        "example": {
            "steps": [
                {"id": "start", "label": "Start", "type": "start"},
                {"id": "review", "label": "Review", "type": "process"},
                {"id": "approve", "label": "Approve?", "type": "decision"},
                {"id": "publish", "label": "Publish", "type": "process"},
                {"id": "end", "label": "End", "type": "end"},
            ],
            "transitions": [
                {"from": "start", "to": "review"},
                {"from": "review", "to": "approve"},
                {"from": "approve", "to": "publish", "label": "yes"},
                {"from": "approve", "to": "review", "label": "no"},
                {"from": "publish", "to": "end"},
            ],
        },
    },
    "sequence": {
        "name": "Sequence Diagram",
        "description": "Message exchange between participants over time",
        "spec_keys": ["participants", "messages"],
        "example": {
            "participants": ["Client", "API", "Database"],
            "messages": [
                {"from": "Client", "to": "API", "label": "GET /users"},
                {"from": "API", "to": "Database", "label": "SELECT *"},
                {"from": "Database", "to": "API", "label": "rows"},
                {"from": "API", "to": "Client", "label": "200 OK"},
            ],
        },
    },
    "dataflow": {
        "name": "Dataflow Diagram",
        "description": "Data movement and transformation between processes",
        "spec_keys": ["processes", "datastores", "flows"],
        "example": {
            "processes": [
                {"id": "ingest", "label": "Ingest"},
                {"id": "transform", "label": "Transform"},
                {"id": "serve", "label": "Serve"},
            ],
            "datastores": [
                {"id": "raw", "label": "Raw Data"},
                {"id": "clean", "label": "Clean Data"},
            ],
            "flows": [
                {"from": "ingest", "to": "raw", "label": "store"},
                {"from": "raw", "to": "transform", "label": "read"},
                {"from": "transform", "to": "clean", "label": "write"},
                {"from": "clean", "to": "serve", "label": "read"},
            ],
        },
    },
    "lifecycle": {
        "name": "Lifecycle Diagram",
        "description": "State transitions and lifecycle phases",
        "spec_keys": ["states", "transitions", "initial_state"],
        "example": {
            "initial_state": "created",
            "states": [
                {"id": "created", "label": "Created", "type": "initial"},
                {"id": "running", "label": "Running", "type": "active"},
                {"id": "paused", "label": "Paused", "type": "suspended"},
                {"id": "stopped", "label": "Stopped", "type": "terminal"},
            ],
            "transitions": [
                {"from": "created", "to": "running", "label": "start"},
                {"from": "running", "to": "paused", "label": "pause"},
                {"from": "paused", "to": "running", "label": "resume"},
                {"from": "running", "to": "stopped", "label": "stop"},
                {"from": "paused", "to": "stopped", "label": "force_stop"},
            ],
        },
    },
}


# ── Agent ────────────────────────────────────────────────────────────────


class AnimationAgent:
    """Diagram and animation generation agent.

    Generates professional diagrams using graphviz (primary) with
    matplotlib/pillow for animation formats (GIF/WebM).
    """

    async def handle_handoff(self, task: dict) -> dict:
        """Route to the requested tool.

        Expected format:
            {"tool": "...", "args": {...}}

        Returns:
            {"status": "ok"|"error", "message": "...", "data": ...}
        """
        tool = task.get("tool", "")
        args = task.get("args", {})

        handlers = {
            "generate_diagram": self._generate_diagram,
            "export_diagram": self._export_diagram,
            "list_templates": self._list_templates,
        }

        handler = handlers.get(tool)
        if handler is None:
            result = {
                "status": "error",
                "message": f"Unknown tool: {tool}. Available: {list(handlers.keys())}",
                "data": None,
            }
        else:
            try:
                result = await handler(args)
            except Exception as e:
                logger.error("Error in tool %s: %s", tool, e)
                result = {"status": "error", "message": str(e), "data": None}
        return json.dumps(result, ensure_ascii=False)

    # ── Tools ──────────────────────────────────────────────────────────

    async def _generate_diagram(self, args: dict) -> dict:
        """Generate a diagram from a type + spec.

        Args:
            type: One of "architecture", "workflow", "sequence", "dataflow", "lifecycle".
            spec: JSON dict with type-specific keys. See list_templates for schema.
        """
        diag_type = args.get("type", "")
        spec = args.get("spec", {})

        if diag_type not in TEMPLATES:
            return {
                "status": "error",
                "message": f"Unknown diagram type: {diag_type}. Available: {list(TEMPLATES.keys())}",
                "data": None,
            }

        spec = self._normalize_spec(diag_type, spec)

        if not _GRAPHVIZ_AVAILABLE:
            return {
                "status": "error",
                "message": (
                    f"graphviz is not installed. Install with:\n"
                    f"  pip install graphviz\n"
                    f"  (system graphviz binary also required: apt install graphviz / brew install graphviz)\n"
                    f"Import error: {_graphviz_import_error}"
                ),
                "data": None,
            }

        diag_id = str(uuid.uuid4())[:8]
        dot_source = self._build_graphviz(diag_type, spec)

        import graphviz

        dot = graphviz.Source(dot_source, format="png")
        dot.attr(rankdir="TB", fontname="Arial", fontsize="11")
        dot.attr("node", fontname="Arial", fontsize="10", shape="box", style="rounded,filled", fillcolor="#e8f0fe")
        dot.attr("edge", fontname="Arial", fontsize="9")

        # Render to bytes
        png_data = dot.pipe(format="png")

        _diagram_store[diag_id] = {
            "id": diag_id,
            "type": diag_type,
            "spec": spec,
            "dot_source": dot_source,
            "png_data": png_data,
        }

        return {
            "status": "ok",
            "message": f"Diagram '{diag_type}' generated (id={diag_id})",
            "data": {
                "diagram_id": diag_id,
                "type": diag_type,
                "dot_source": dot_source,
                "preview_base64": base64.b64encode(png_data).decode("ascii"),
            },
        }

    async def _export_diagram(self, args: dict) -> dict:
        """Export a generated diagram to a file.

        Args:
            diagram_id: The diagram ID from generate_diagram.
            format: "png", "jpeg", "svg", "gif", "webm". Default "png".
            output_path: Optional output file path. Defaults to a temp file.
        """
        diag_id = args.get("diagram_id")
        fmt = args.get("format", "png").lower()
        output_path = args.get("output_path")

        if diag_id not in _diagram_store:
            return {"status": "error", "message": f"Unknown diagram_id: {diag_id}", "data": None}

        valid_formats = ["png", "jpeg", "jpg", "svg", "gif", "webm"]
        if fmt not in valid_formats:
            return {"status": "error", "message": f"Invalid format: {fmt}. Use: {valid_formats}", "data": None}

        entry = _diagram_store[diag_id]

        # Normalize jpg → jpeg
        fmt_normalized = "jpeg" if fmt == "jpg" else fmt

        if fmt_normalized in ("png", "jpeg", "svg"):
            return await self._export_static(entry, fmt_normalized, output_path)
        elif fmt_normalized in ("gif", "webm"):
            return await self._export_animated(entry, fmt_normalized, output_path)
        else:
            return {"status": "error", "message": f"Unsupported format: {fmt}", "data": None}

    async def _list_templates(self, _args: dict) -> dict:
        """List all available diagram templates with their schemas."""
        return {
            "status": "ok",
            "message": f"{len(TEMPLATES)} template(s) available",
            "data": {"templates": TEMPLATES},
        }

    # ── Internal: Graphviz builders ────────────────────────────────────

    def _build_graphviz(self, diag_type: str, spec: dict) -> str:
        """Build DOT source from spec, by type."""
        builders = {
            "architecture": self._build_architecture,
            "workflow": self._build_workflow,
            "sequence": self._build_sequence,
            "dataflow": self._build_dataflow,
            "lifecycle": self._build_lifecycle,
        }
        return builders[diag_type](spec)

    def _build_architecture(self, spec: dict) -> str:
        lines = ["digraph Architecture {", "  rankdir=TB;", '  label="System Architecture";']
        lines.append("  fontsize=14;")

        # Layer grouping
        layers = spec.get("layers", [])
        for layer in layers:
            lines.append(f'  subgraph cluster_{layer["id"]} {{')
            lines.append(f'    label="{layer.get("label", layer["id"])}";')
            lines.append('    style=filled;')
            lines.append('    fillcolor="#f0f4f8";')
            for comp in spec.get("components", []):
                if comp.get("layer") == layer["id"]:
                    lines.append(f'    {comp["id"]} [label="{comp["label"]}"];')
            lines.append("  }")

        # Orphan components (no layer)
        layered_ids = {c["id"] for c in spec.get("components", []) if c.get("layer")}
        for comp in spec.get("components", []):
            if comp["id"] not in layered_ids:
                lines.append(f'  {comp["id"]} [label="{comp["label"]}"];')

        # Connections
        for conn in spec.get("connections", []):
            label = conn.get("label", "")
            if label:
                lines.append(f'  {conn["from"]} -> {conn["to"]} [label="{label}"];')
            else:
                lines.append(f'  {conn["from"]} -> {conn["to"]};')

        lines.append("}")
        return "\n".join(lines)

    def _build_workflow(self, spec: dict) -> str:
        lines = ["digraph Workflow {", "  rankdir=TB;", '  label="Workflow";', "  fontsize=14;"]

        node_styles = {
            "start": 'shape=circle,fillcolor="#c8e6c9",style=filled',
            "end": 'shape=doublecircle,fillcolor="#ffcdd2",style=filled',
            "decision": 'shape=diamond,fillcolor="#fff9c4",style=filled',
            "process": 'shape=box,style="rounded,filled",fillcolor="#e3f2fd"',
        }

        for step in spec.get("steps", []):
            style = node_styles.get(step.get("type", "process"), node_styles["process"])
            lines.append(f'  {step["id"]} [label="{step["label"]}",{style}];')

        for trans in spec.get("transitions", []):
            label = trans.get("label", "")
            if label:
                lines.append(f'  {trans["from"]} -> {trans["to"]} [label="{label}"];')
            else:
                lines.append(f'  {trans["from"]} -> {trans["to"]};')

        lines.append("}")
        return "\n".join(lines)

    def _build_sequence(self, spec: dict) -> str:
        """Sequence diagram rendered as a flow of messages with lifelines."""
        lines = ["digraph Sequence {", "  rankdir=TB;", '  label="Sequence Diagram";', "  fontsize=14;"]

        participants = spec.get("participants", [])
        # Create lifeline nodes (invisible connections force ordering)
        prev = None
        for p in participants:
            safe = p.replace(" ", "_").replace("-", "_")
            lines.append(f'  {safe} [label="{p}",shape=box,style="rounded,filled",fillcolor="#e8eaf6"];')
            if prev:
                lines.append(f"  {prev} -> {safe} [style=invis];")
            prev = safe

        # Numbered messages
        for i, msg in enumerate(spec.get("messages", [])):
            from_id = msg["from"].replace(" ", "_").replace("-", "_")
            to_id = msg["to"].replace(" ", "_").replace("-", "_")
            label = msg.get("label", f"msg_{i+1}")
            lines.append(f'  {from_id} -> {to_id} [label="{i+1}. {label}",fontsize=9];')

        lines.append("}")
        return "\n".join(lines)

    def _build_dataflow(self, spec: dict) -> str:
        lines = ["digraph Dataflow {", "  rankdir=LR;", '  label="Dataflow Diagram";', "  fontsize=14;"]

        # Processes
        for proc in spec.get("processes", []):
            lines.append(f'  {proc["id"]} [label="{proc["label"]}",shape=box,fillcolor="#e3f2fd",style=filled];')

        # Datastores
        for ds in spec.get("datastores", []):
            lines.append(f'  {ds["id"]} [label="{ds["label"]}",shape=cylinder,fillcolor="#fff3e0",style=filled];')

        # Data flows
        for flow in spec.get("flows", []):
            label = flow.get("label", "")
            lines.append(f'  {flow["from"]} -> {flow["to"]} [label="{label}",fontsize=9];')

        lines.append("}")
        return "\n".join(lines)

    def _build_lifecycle(self, spec: dict) -> str:
        lines = ["digraph Lifecycle {", "  rankdir=LR;", '  label="Lifecycle States";', "  fontsize=14;"]

        node_styles = {
            "initial": 'fillcolor="#c8e6c9",style=filled',
            "active": 'fillcolor="#bbdefb",style="rounded,filled"',
            "suspended": 'fillcolor="#fff9c4",style="rounded,filled"',
            "terminal": 'fillcolor="#ffcdd2",style="rounded,filled"',
        }

        for state in spec.get("states", []):
            style = node_styles.get(state.get("type", "active"), node_styles["active"])
            lines.append(f'  {state["id"]} [label="{state["label"]}",shape=box,{style}];')

        for trans in spec.get("transitions", []):
            label = trans.get("label", "")
            lines.append(f'  {trans["from"]} -> {trans["to"]} [label="{label}",fontsize=9];')

        lines.append("}")
        return "\n".join(lines)

    # ── Export helpers ─────────────────────────────────────────────────

    async def _export_static(self, entry: dict, fmt: str, output_path: str | None) -> dict:
        import graphviz

        dot = graphviz.Source(entry["dot_source"], format=fmt)
        dot.attr(rankdir="TB", fontname="Arial", fontsize="11")
        dot.attr("node", fontname="Arial", fontsize="10", shape="box", style="rounded,filled", fillcolor="#e8f0fe")
        dot.attr("edge", fontname="Arial", fontsize="9")

        data = dot.pipe(format=fmt)

        if not output_path:
            suffix = ".svg" if fmt == "svg" else f".{fmt}"
            output_path = os.path.join(tempfile.gettempdir(), f"diagram_{entry['id']}{suffix}")

        with open(output_path, "wb") as f:
            f.write(data)

        return {
            "status": "ok",
            "message": f"Diagram exported to {output_path}",
            "data": {
                "diagram_id": entry["id"],
                "format": fmt,
                "output_path": output_path,
                "size_bytes": len(data),
            },
        }

    async def _export_animated(self, entry: dict, fmt: str, output_path: str | None) -> dict:
        """Generate animated GIF/WebM from multiple frames using matplotlib + pillow."""
        if not _MATPLOTLIB_AVAILABLE:
            return {
                "status": "error",
                "message": (
                    "matplotlib and pillow are needed for animated exports. Install:\n"
                    f"  pip install matplotlib pillow\n"
                    f"Import error: {_matplotlib_import_error}"
                ),
                "data": None,
            }

        import io

        import matplotlib.animation as animation
        import matplotlib.pyplot as plt
        from PIL import Image

        # Generate frames — animate the diagram spec as a sequence of build stages
        frames = self._build_animation_frames(entry)

        if not frames:
            return {"status": "error", "message": "No frames could be generated from spec", "data": None}

        # Render frames as images
        import graphviz
        frame_images = []
        for frame_spec in frames:
            dot_source = self._build_graphviz(entry["type"], frame_spec)
            dot = graphviz.Source(dot_source, format="png")
            dot.attr(rankdir="TB", fontname="Arial")
            png = dot.pipe(format="png")
            frame_images.append(Image.open(io.BytesIO(png)))

        if not output_path:
            suffix = ".gif" if fmt == "gif" else ".webm"
            output_path = os.path.join(tempfile.gettempdir(), f"diagram_{entry['id']}_anim{suffix}")

        if fmt == "gif":
            # Save as animated GIF using pillow
            frame_images[0].save(
                output_path,
                save_all=True,
                append_images=frame_images[1:],
                duration=800,
                loop=0,
            )
        elif fmt == "webm":
            # Save individual frames, instruct user to use ffmpeg
            frame_dir = os.path.join(tempfile.gettempdir(), f"frames_{entry['id']}")
            os.makedirs(frame_dir, exist_ok=True)
            for i, img in enumerate(frame_images):
                img.save(os.path.join(frame_dir, f"frame_{i:04d}.png"))
            return {
                "status": "ok",
                "message": f"Frames saved to {frame_dir}. Run: ffmpeg -framerate 2 -i {frame_dir}/frame_%04d.png {output_path}",
                "data": {
                    "diagram_id": entry["id"],
                    "format": "webm",
                    "frame_dir": frame_dir,
                    "frame_count": len(frame_images),
                    "ffmpeg_command": f"ffmpeg -framerate 2 -i {frame_dir}/frame_%04d.png {output_path}",
                },
            }

        return {
            "status": "ok",
            "message": f"Animated diagram exported to {output_path}",
            "data": {
                "diagram_id": entry["id"],
                "format": fmt,
                "output_path": output_path,
                "frame_count": len(frame_images),
            },
        }

    def _build_animation_frames(self, entry: dict) -> list[dict]:
        """Decompose a static spec into progressive build stages for animation."""
        spec = entry["spec"]
        diag_type = entry["type"]
        frames = []

        if diag_type == "architecture":
            components = spec.get("components", [])
            connections = spec.get("connections", [])
            layers = spec.get("layers", [])
            # Frame 1: layers only
            frames.append({"components": [], "connections": [], "layers": layers})
            # Progressive component reveal
            for i in range(1, len(components) + 1):
                visible_comps = components[:i]
                visible_conns = [c for c in connections if c["from"] in {x["id"] for x in visible_comps} and c["to"] in {x["id"] for x in visible_comps}]
                frames.append({"components": visible_comps, "connections": visible_conns, "layers": layers})
        elif diag_type == "workflow":
            steps = spec.get("steps", [])
            transitions = spec.get("transitions", [])
            for i in range(1, len(steps) + 1):
                visible_steps = steps[:i]
                visible_trans = [t for t in transitions if t["from"] in {s["id"] for s in visible_steps} and t["to"] in {s["id"] for s in visible_steps}]
                frames.append({"steps": visible_steps, "transitions": visible_trans})
        elif diag_type == "lifecycle":
            states = spec.get("states", [])
            transitions = spec.get("transitions", [])
            for i in range(1, len(states) + 1):
                visible_states = states[:i]
                visible_trans = [t for t in transitions if t["from"] in {s["id"] for s in visible_states} and t["to"] in {s["id"] for s in visible_states}]
                frames.append({"states": visible_states, "transitions": visible_trans, "initial_state": spec.get("initial_state", "")})
        else:
            # Fallback: single frame
            frames.append(spec)

        return frames

    # ── Spec normalization ─────────────────────────────────────────────

    def _normalize_spec(self, diag_type: str, spec: dict) -> dict:
        """Ensure spec has the minimum required structure."""
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except json.JSONDecodeError:
                spec = {}

        # Set defaults based on type
        if diag_type == "architecture":
            spec.setdefault("components", [])
            spec.setdefault("connections", [])
            spec.setdefault("layers", [])
        elif diag_type == "workflow":
            spec.setdefault("steps", [])
            spec.setdefault("transitions", [])
        elif diag_type == "sequence":
            spec.setdefault("participants", [])
            spec.setdefault("messages", [])
        elif diag_type == "dataflow":
            spec.setdefault("processes", [])
            spec.setdefault("datastores", [])
            spec.setdefault("flows", [])
        elif diag_type == "lifecycle":
            spec.setdefault("states", [])
            spec.setdefault("transitions", [])
            spec.setdefault("initial_state", "")

        return spec
