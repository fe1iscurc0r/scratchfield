import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const MAC_SIGN_IDENTITY = "-";

async function run(cmd, args) {
  const { stdout, stderr } = await execFileAsync(cmd, args);
  if (stdout.trim()) {
    process.stdout.write(stdout);
  }
  if (stderr.trim()) {
    process.stderr.write(stderr);
  }
}

function walkDirs(root) {
  const stack = [root];
  const dirs = [];
  while (stack.length > 0) {
    const current = stack.pop();
    dirs.push(current);
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      if (entry.isDirectory() && !entry.isSymbolicLink()) {
        stack.push(join(current, entry.name));
      }
    }
  }
  return dirs;
}

function collectNestedSignTargets(appPath) {
  const targets = [];
  for (const dir of walkDirs(appPath)) {
    if (dir === appPath) {
      continue;
    }
    if (dir.endsWith(".app") || dir.endsWith(".framework")) {
      targets.push(dir);
      continue;
    }
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isFile() || entry.isSymbolicLink()) {
        continue;
      }
      if (entry.name.endsWith(".dylib")) {
        targets.push(join(dir, entry.name));
      }
    }
  }
  targets.sort((a, b) => b.split("/").length - a.split("/").length);
  return [...new Set(targets)];
}

async function signPath(targetPath) {
  process.stdout.write(`[afterPack] ad-hoc signing ${targetPath}\n`);
  await run("codesign", ["--force", "--sign", MAC_SIGN_IDENTITY, "--timestamp=none", targetPath]);
}

export default async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") {
    return;
  }

  const appPath = join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`,
  );
  if (!existsSync(appPath)) {
    throw new Error(`[afterPack] app not found: ${appPath}`);
  }

  const nestedTargets = collectNestedSignTargets(appPath);
  process.stdout.write(`[afterPack] nested sign targets: ${nestedTargets.length}\n`);
  for (const target of nestedTargets) {
    await signPath(target);
  }
  await signPath(appPath);
  await run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
}
