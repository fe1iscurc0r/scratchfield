# scratchfield — The Experimental Field

> Connection is justice; control is destruction.
> Integration hell isn't an accident — it's a feature. We pull inspiration from others, pollinate it into our own soil, and grow it into something ours.
> We don't slap a logo on other people's work — every component carries a fusion report: origin, license, modifications, acceptance. In black and white.

**scratchfield** (实验田, "The Experimental Field") — a showcase of integration engineering built on the **Pollination** methodology, plus a plugin marketplace. Active development happens in a private working repo; this repo is the public showcase, updated by milestone snapshots. **Current snapshot: 2026-09-30.**

## What is this

In one sentence: **pollinating good ideas from upstream projects into our own system, and growing them into our own things.**

Pollination is not fork-paste. It's "dissect → adapt → integrate → leave a report". Every pollinated component is registered with its origin, license, modification points, and acceptance results. The license ledger lives in `github_haul/FUSION-LOG-2026-08-16.md` and the full third-party copyright collection in [NOTICE](NOTICE).

### Core homegrown assets (the main course)

- **Tool Bus** (`mcpserver/`) — MCP adaptation layer with unified registration / scheduling / auth. Homegrown, with multi-domain tool wrappers and an agent-manifest contract.
- **RF Brain** (`mcpserver/rf_brain/`) — protocol-agnostic RF demodulation chain. Homegrown: OOK decoder family (Acurite/LaCrosse/PWM/PPM/Manchester), DSP filter chain, dcp binary frames, sentinel bridge ingestion.
- **radio_suite** — FT8/WSPR/SSTV/NOAA APT decoding, SDR spectrum panel, APRS iGate, IC-705 CI-V rig control. An independent component wired into the main body via the bus.
- **Sentinel Grid firmware** (`firmware/`) — ESP32-S3 + SX1278 edge spectrum sentinels. The complete chain from antenna to memory for 433MHz sensor signals. Homegrown.
- **Research Workbench** — ELN experiment records, literature library, materials data workbench (TGA/DSC/XRD), material property prediction pipeline; a domain-pack mechanism (`domains/`) enables multi-discipline extension.
- **Pollination Plugin Marketplace** (`plugins/`) — every pollinated component is registered here. Free to add, plug-and-play.
- **Memory Hooks** (`hooks/`) — fact indexing / contradiction detection / supersedes edges. Homegrown.
- **NEKO Integration** (`NEKO/`) — **flagship pollination case**: the Apache-2.0 upstream NEKO desktop pet as the body layer (Live2D/TTS/ASR/vision), with a homegrown integration layer (launcher wrapper, provider overlay, injection routing, soul bridge) wiring it into our own persona core (memory / RAG / decision) and agent ecosystem.

### Recent highlights (2026-09 snapshot)

- **Domain-pack mechanism landed** — `domains/` declares ELN fields / paper fields / tagging schemes per discipline; materials and law packs in production; a minimal template exists for a third domain
- **radio_suite went from SPEC to real hardware** — SPEC-17 six workorders merged: FT8/WSPR/NOAA satellite image decoding, live spectrum panel (WebSocket waterfall), IC-705 panel integration
- **LoRaCanary sentinel board v1.1 finalized** — a fully-socketed board with AI-assisted PCB layout; SPEC-20 series in progress
- **Material property prediction pipeline** — ELN export → feature matrix → baseline models → CLI prediction with uncertainty intervals
- **Three-layer toolchain optimization** — lazy registration / call profiling & circuit breaking / declarative chain orchestration; a (verb, domain) capability index across 54 manifests
- **Monolith decomposition & governance** — six 2000+ line monoliths split into domain modules; system self-governance tooling (structure snapshots / critical paths / trend forecasting) in-repo
- **One-command health checks** — `scripts/doctor.py` app-level self-check + `doctor_env.py` environment check; whatever step broke, you'll see it at a glance

### Identity statement

- This repo is a **pollination experimental field**, not a shell over any upstream. The underlying engines (NagaAgent, NEKO, llama.cpp and other Apache/MIT components) are part of the tech stack, credited per component; what we produce is the integration layer, the tool bus, the RF/firmware, the pollinated plugins.
- Analogy: Chrome is built on Chromium, Firefox on Gecko — the engine is the engine, the brand is the brand. What we're good at is "digesting upstream into our own".
- Origin and license boundaries of every pollinated entry are in the FUSION-LOG and each plugin entry. Clean on both law and ethics.

## What pollination is

Pollination = upstream inspiration → dissect → adapt → integrate. Not fork-paste — only "the part that can grow into our system" is transplanted, and a complete pollination report (origin / license / modification points / acceptance) is left behind. The license ledger lives in `github_haul/FUSION-LOG-2026-08-16.md`.

## Repository map

| Path | Contents |
|------|------|
| `mcpserver/` | Tool bus (homegrown, incl. rf_brain RF brain) |
| `apiserver/` | FastAPI main backend (ELN/papers/data tools/persona/memory) |
| `frontend/` | Vue 3 desktop shell (spectrum panel / data workbench / settings) |
| `domains/` | Domain packs (materials/law, extensible to a third) |
| `firmware/` | ESP32 firmware (Sentinel Grid, homegrown) |
| `plugins/` | Pollination plugin marketplace (registry + add/install scripts) |
| `hooks/` | Memory hooks (fact indexing / contradiction detection, homegrown) |
| `NEKO/` | NEKO integration (flagship pollination case: upstream body + homegrown integration layer) |
| `skills/` | 190+ skill library (research/radio decoupled) |
| `docs/` | Architecture / pollination reports / SPECs |
| `github_haul/` | Sourcing index + license ledger |
| `scripts/` | Tooling (plugin add/install/health checks) |

## Quick start

For launching the integrated body, see `NEKO/N.E.K.O/README.MD`. For the plugin marketplace, see `plugins/README.md`.

```bash
# Environment check (before installing)
python doctor_env.py
# Browse the marketplace
cat plugins/index.json
# Install a plugin into the runtime
./scripts/plugin-install.sh <plugin-id>
# App-level check (after installing)
python scripts/doctor.py --quick
```

## The story

The full origin, methodology, and evolution of this repo: [STORY.md](STORY.md) — the record of an experiment that started as a summer-break planner and grew into a system pollinated from dozens of open-source projects.

## License

AGPL-3.0 (see LICENSE). Commercial use in closed source requires separate authorization. **The complete third-party copyright and license notices live in [NOTICE](NOTICE)**; each plugin entry and the FUSION-LOG also carry per-component records.

---

Maintained by fe1iscurc0r · The Experimental Field, snapshot updates (2026-09-30)
