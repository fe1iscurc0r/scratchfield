import { register } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve as resolvePath } from "node:path";

const moduleDir = dirname(fileURLToPath(import.meta.url));
const resolverUrl = pathToFileURL(resolvePath(moduleDir, "source_resolver.mjs"));

// Use the current working directory as the loader base so relative imports
// inside vendor/openclaw resolve exactly the same in build-time checks and
// packaged runtime startup.
register(resolverUrl, pathToFileURL(`${process.cwd()}/`));
