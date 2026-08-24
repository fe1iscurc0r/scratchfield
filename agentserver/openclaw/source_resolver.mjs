import { access } from "node:fs/promises";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REMAP_SUFFIXES = new Map([
  [".js", [".ts", ".tsx"]],
  [".mjs", [".mts", ".ts", ".tsx"]],
  [".cjs", [".cts", ".ts", ".tsx"]],
]);

async function fileExists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function isRelativePath(specifier) {
  return specifier.startsWith("./") || specifier.startsWith("../");
}

function isFileUrl(specifier) {
  return specifier.startsWith("file://");
}

function isAbsolutePath(specifier) {
  return specifier.startsWith("/");
}

function remapSuffixes(specifier) {
  for (const [suffix, replacements] of REMAP_SUFFIXES.entries()) {
    if (!specifier.endsWith(suffix)) {
      continue;
    }
    const base = specifier.slice(0, -suffix.length);
    return replacements.map((replacement) => `${base}${replacement}`);
  }
  return [];
}

function buildCandidatePaths(specifier, parentURL) {
  if (isRelativePath(specifier)) {
    if (!parentURL) {
      return [];
    }
    const parentDir = dirname(fileURLToPath(parentURL));
    return remapSuffixes(specifier).map((candidateSpecifier) => resolvePath(parentDir, candidateSpecifier));
  }

  if (isFileUrl(specifier)) {
    const rawPath = fileURLToPath(specifier);
    return remapSuffixes(rawPath).map((candidatePath) => resolvePath(candidatePath));
  }

  if (isAbsolutePath(specifier)) {
    return remapSuffixes(specifier).map((candidatePath) => resolvePath(candidatePath));
  }

  return [];
}

export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    if (error?.code !== "ERR_MODULE_NOT_FOUND") {
      throw error;
    }
    for (const candidatePath of buildCandidatePaths(specifier, context.parentURL)) {
      if (!(await fileExists(candidatePath))) {
        continue;
      }
      return {
        shortCircuit: true,
        url: pathToFileURL(candidatePath).href,
      };
    }
    throw error;
  }
}
