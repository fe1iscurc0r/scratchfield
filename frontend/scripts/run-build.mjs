import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'

const cwd = process.cwd()
const bundledNodeCandidates = process.platform === 'win32'
  ? [
      resolve(cwd, 'backend-dist/runtime/node/node.exe'),
      resolve(cwd, 'backend-dist/runtime/node/node.cmd'),
    ]
  : [
      resolve(cwd, 'backend-dist/runtime/node/bin/node'),
      resolve(cwd, 'backend-dist/runtime/node/node'),
    ]
const bundledNode = bundledNodeCandidates.find(candidate => existsSync(candidate))
const nodeExec = bundledNode ?? process.execPath

const commands = [
  [resolve(cwd, 'node_modules/vue-tsc/bin/vue-tsc.js'), '-b'],
  [resolve(cwd, 'node_modules/vite/bin/vite.js'), 'build'],
]

for (const args of commands) {
  const result = spawnSync(nodeExec, args, {
    cwd,
    stdio: 'inherit',
  })

  if (result.error) {
    throw result.error
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}
