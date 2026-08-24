---
name: openreason
description: Run structured, verifiable LLM reasoning through a classify → skeleton → solve → verify → finalize pipeline. Use when the user needs reliable multi-step reasoning (math, logic, ethics, philosophy) and wants transparent steps, self-checking, and a confidence-scored verdict instead of a single raw model answer.
---

# OpenReason Skill

Orchestrate a multi-model reasoning pipeline that classifies the question, builds a formal reasoning skeleton, solves each substep, verifies the result (including a critic pass), and finalizes a verdict. This gives transparent, reproducible, self-corrected reasoning on top of any LLM provider — the "second reasoning line" beyond raw LLM output for scratchpad.

> Requires the `openreason` npm package and a paid LLM API key (OpenAI / Anthropic / Google / xAI / DeepSeek). Use `--provider mock` to exercise the pipeline offline without an API key.

## Workflow

1. **Classify** — determine domain (math / logic / ethics / philosophy / general), difficulty, depth, and mode (reflex / analytic / reflective).
2. **Skeleton** — emit a JSON reasoning plan: `{ claim, substeps: [...], expectedChecks: [...] }`.
3. **Solve** — execute each substep with retries, using a simple model for reflex tasks and a complex model for reflective tasks to control cost.
4. **Verify** — check numeric equality, contradictions, rule/quantifier consistency, missing steps; run a critic model pass; repair and rerun broken steps.
5. **Finalize** — aggregate into `{ verdict, confidence, mode, metadata }`.

## Usage

```bash
# CLI (auto-loads .env)
npx openreason "prove that sqrt(2) is irrational"
npx openreason --provider google --model gemini-2.5-flash "show the product of two even numbers is even"
npx openreason --provider mock "offline smoke test"          # no API key needed

# SDK
import openreason from "openreason";
openreason.init({
  provider: "google",
  apiKey: "...",
  model: "gemini-2.5-flash",
  simpleModel: "gemini-2.0-flash",   // reflex tasks
  complexModel: "gemini-2.5-flash",  // reflective tasks
  memory: { enabled: true, path: "./data/memory.db" },
});
const result = await openreason.reason("is 9991 a prime number");
console.log(result.verdict, result.confidence, result.mode);
```

## Mode selection (automatic)

- **Reflex** — fast single-step; small math, easy logic, factual checks.
- **Analytic** — structured with scratchpads; medium math, multi-step logic, short proofs.
- **Reflective** — full chain-of-thought with verification; hard proofs, ethics, philosophy.

## Verification focus

- **Math**: symbolic equality, numeric error bounds, monotonicity, contradictions.
- **Logic**: implication direction, quantifier consistency, contradictions, missing premises.
- **Structural**: missing steps, incomplete conclusions, invalid reasoning jumps.
- **Critic**: one extra model call to catch what the solver missed; can repair and rerun.

## Cost / performance tips

- Use a flash/simple model for skeletons and reflex tasks; a strong model only for reflective tasks.
- Enable memory to avoid recomputing; set `maxRetries: 1` if cost is a priority.
- Limit reflective mode when unnecessary.

## References

- Source repo: `knowledge/OpenReason/` (Apache-2.0)
- Pipeline core: `src/core/` (classifier / skeleton / solver / verifier / finalizer)
- Prompt overrides: `public/prompt.json`