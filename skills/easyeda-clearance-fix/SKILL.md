---
name: easyeda-clearance-fix
description: Fix remaining clearance/track/via errors on an already routed EasyEDA Pro PCB. Use when `pcb check` reports a small number of electrical spacing issues and you need to locally move tracks/vias rather than re-route the whole board.
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
  version: "1.0"
  skill-author: LoRaCanary team
  tags: [pcb, easyeda, drc, clearance, routing, via]
---

# easyeda-clearance-fix

> Fix a small set of `clearance`, `track-over-pad`, or `via-in-pad` errors on an already routed EasyEDA Pro PCB without ripping up the whole board.

## When to Use This Skill

Invoke this skill when:

- `easyeda pcb check --json` reports a small number of **ERROR** items (1–20).
- The errors are all spacing/location related (clearance, via too close to pad, track crossing pad, etc.).
- You can fix them by **moving a few tracks or vias a small distance** rather than rerouting entire nets.
- Do **not** use this skill for schematic errors, component placement, or when the board has hundreds of clearance errors (then use `pcb autoroute` or redo placement first).

## Workflow

### 1. Snapshot

Before changing anything, get the current state:

```bash
# Dump board geometry and netlist
easyeda pcb dump --project <PROJECT> --json > pcb_dump.json

# List tracks and vias
easyeda pcb track-list --project <PROJECT> --json > tracks.json
easyeda pcb via-list  --project <PROJECT> --json > vias.json
```

Record for each offending item:

- `primitiveId`
- `layer` (1=Top, 2=Bottom, 15/16=inner)
- `net`
- `startX/startY/endX/endY`
- `width`
- connected `via` coordinates

Or let the companion tool do both steps automatically (computes edge-to-edge
clearance and prints violating primitiveId pairs, worst-first):

```bash
python scripts/easyeda/clearance_fix.py <PROJECT> --violations        # default rule 6 mil
python scripts/easyeda/clearance_fix.py <PROJECT> --violations 8      # custom rule
```

### 2. Plan

For each clearance error:

1. Identify the two primitives involved.
2. Decide which one to move.
3. Choose new coordinates with at least `DRC_rule + 1 mil` extra margin.
4. If a via is too close to a pad, move the via **along the direction away from the pad** (usually the shortest path to clear the pad edge).

### 3. Decide Whether to Patch or Roll Back

If the fix requires more than **3 small track/via moves**, or if you notice any of these signs, **stop patching and roll back**:

- The number of `No Connection` errors goes up after a patch.
- `pcb check` reports new ERROR objects that did not exist before the patch.
- You are about to place a via on an SMD pad (via-in-pad).

When this happens:

1. Delete only the new primitives you just created.
2. Restore the board to the last known good state (rip-up the net and run autorouter, or use the snapshot from step 1).
3. Report the rollback and ask the user whether to proceed with full re-route or let them edit manually.

### 4. Authorize Routing Stage

```bash
# Use a realistic assembly profile; do NOT use 0 mil to bypass.
easyeda pcb stage set-assembly \
  --project <PROJECT> \
  --profile reflow \
  --min-gap 6 \
  --large-pad-access 12

# Pass the gate
easyeda pcb layout-lint --gate --min-score 0 --max-crossings -1 --project <PROJECT>

# Confirm
easyeda pcb stage confirm-layout --project <PROJECT> --force "placement ok" --note "..."
easyeda pcb stage confirm-outline --project <PROJECT> --note "outline ok"
```

### 5. Delete Old Primitives

Delete all tracks and vias you are going to replace **in one call**:

```bash
easyeda pcb delete --project <PROJECT> --ids <id1,id2,...>
```

### 6. Re-authorize Stage

`delete` resets routing authorization. Run step 4 again.

### 7. Create New Tracks / Vias

Create new tracks/vias **without any `doc reload` in between**:

```bash
# Example: create a track on the bottom layer
easyeda pcb track \
  --project <PROJECT> \
  --x1 4321.474 --y1 2130 \
  --x2 2332.1   --y2 2130 \
  --net CC2 \
  --width 10 \
  --layer 2

# Example: create a via
easyeda pcb via \
  --project <PROJECT> \
  --x 2845 --y 2628.7664 \
  --net SDA
```

Rules:

- If the original long segment was on an inner/bottom layer, keep it on the same layer.
- Use `layer 1` for Top, `layer 2` for Bottom, `layer 15`/`16` for inner planes.
- Prefer orthogonal tracks (L-shapes) over diagonals to keep DRC predictable.

### 8. Verify

Now reload once and run check:

```bash
easyeda doc reload --project <PROJECT>
easyeda pcb check --project <PROJECT> --json > check.json
```

Parse `findings`:

```python
import json
with open("check.json") as f:
    data = json.load(f)
errors = [f for f in data["findings"] if f["level"] == "ERROR"]
print(f"ERRORs: {len(errors)}")
for e in errors:
    print(e["type"], e.get("at"), e["message"])
```

## Common Pitfalls

- **Moving a track to the wrong layer**: always verify the original primitive's `layer` first.
- **`doc reload` between edits**: invalidates routing stage; reload only at final verification.
- **Forgetting stage re-authorize after `delete`**: delete resets the routing gate; you must re-run step 4 before creating new tracks.
- **Using 0 mil assembly profile**: bypasses real DRC/assembly checks; use a realistic value like 6 mil for SMT boards.
- **Too-tight moves**: add at least 1 mil margin beyond the DRC rule to avoid rounding-related false positives.
- **Patching until the board fragments**: if `No Connection` count increases or new ERRORs appear after a patch, stop and roll back; do not keep stitching fragments.
- **Via-in-pad on SMD pads**: never place a through-hole via on an SMD pad unless the design specifically calls for it.

## Output

- Updated PCB document with the targeted clearance fixes.
- `check.json` summary showing remaining ERROR/WARN.
- Optional short note in the project log about what was moved and why.

## Example Scenario

> `pcb check` reports `CC2 / VBUS` clearance of 4.2 mil at J1.

1. `track-list` shows CC2 long segment is on **layer 2** (Bottom).
2. Decide to keep CC2 on Bottom and move the horizontal segment from `y=2113` to `y=2140` to clear VBUS.
3. Place new vias at the ends of the moved segment.
4. Re-run `pcb check`.

## References

- Project lesson: `docs/LESSONS_LEARNED.md` L-08 ~ L-13
- Case report: `docs/CASE-27-easyeda-clearance-fix.md`
- Helper script: `scripts/easyeda/clearance_fix.py`
