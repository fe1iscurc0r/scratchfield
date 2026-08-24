/**
 * OpenClaw Gateway 最小启动脚本
 *
 * 由 NagaAgent 的 EmbeddedRuntime 通过 `node gateway_start.mjs` 拉起。
 * 直接调用 startGatewayServer()，跳过 CLI 层，启动更快、日志更干净。
 *
 * 搜索顺序：
 *   compiled-first：
 *     1. OPENCLAW_GATEWAY_VENDOR_ROOT/dist/
 *     2. fallback vendor/openclaw/dist/
 *     3. OPENCLAW_GATEWAY_VENDOR_ROOT/src/
 *   source-first：
 *     1. OPENCLAW_GATEWAY_VENDOR_ROOT/src/
 *     2. fallback vendor/openclaw/src/
 *     3. OPENCLAW_GATEWAY_VENDOR_ROOT/dist/
 *
 * 环境变量：
 *   OPENCLAW_GATEWAY_PORT  — 端口号（默认 20789）
 */

import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const preferSource =
  process.env.OPENCLAW_GATEWAY_ENTRY_MODE === "source"
  || process.execArgv.includes("tsx");
const explicitVendorRoot = process.env.OPENCLAW_GATEWAY_VENDOR_ROOT
  ? resolve(process.env.OPENCLAW_GATEWAY_VENDOR_ROOT)
  : null;
const rootCandidates = explicitVendorRoot
  ? [explicitVendorRoot]
  : [
      __dirname,
      join(__dirname, "..", "..", "vendor", "openclaw"),
    ];

// 按优先级查找 gateway server 入口
let serverPath = null;
const candidates = [];
for (const root of rootCandidates) {
  const sourceEntry = join(root, "src", "gateway", "server.ts");
  const compiledEntry = join(root, "dist", "gateway", "server.js");
  if (preferSource) {
    candidates.push(sourceEntry, compiledEntry);
  } else {
    candidates.push(compiledEntry, sourceEntry);
  }
}

for (const p of candidates) {
  if (existsSync(p)) { serverPath = p; break; }
}

if (!serverPath) {
  process.stderr.write("[gateway_start] fatal: cannot find openclaw gateway entry\n");
  process.stderr.write(`[gateway_start] searched:\n${candidates.map(p => "  - " + p).join("\n")}\n`);
  process.exit(1);
}

const isTsSource = serverPath.endsWith(".ts");
if (isTsSource) {
  process.stderr.write(`[gateway_start] entry mode: ${preferSource ? "source-first" : "compiled-first"}\n`);
  process.stderr.write(`[gateway_start] using source (tsx): ${serverPath}\n`);
} else {
  process.stderr.write(`[gateway_start] entry mode: ${preferSource ? "source-first" : "compiled-first"}\n`);
  process.stderr.write(`[gateway_start] using compiled: ${serverPath}\n`);
}

const { startGatewayServer } = await import(pathToFileURL(serverPath).href);

const port = parseInt(process.env.OPENCLAW_GATEWAY_PORT || "20789", 10);
process.stdout.write(`[gateway_start] starting on port ${port}\n`);

try {
  const server = await startGatewayServer(port, {
    bind: "loopback",
    controlUiEnabled: false,
  });

  process.stdout.write(`[gateway_start] ready on port ${port}\n`);

  const shutdown = async (sig) => {
    process.stdout.write(`[gateway_start] received ${sig}, shutting down\n`);
    try { await server.close({ reason: `received ${sig}` }); } catch {}
    process.exit(0);
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));

} catch (err) {
  process.stderr.write(`[gateway_start] fatal: ${err}\n`);
  if (err.stack) process.stderr.write(err.stack + "\n");
  process.exit(1);
}
