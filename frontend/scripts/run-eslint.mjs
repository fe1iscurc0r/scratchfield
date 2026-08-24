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
const eslintBin = resolve(cwd, 'node_modules/eslint/bin/eslint.js')
const defaultTargets = ['src', 'electron', 'eslint.config.js', 'vite.config.ts']
const forwardedArgs = process.argv.slice(2)
const nodeExec = bundledNode ?? process.execPath
const eslintArgs = [eslintBin, ...defaultTargets, ...forwardedArgs]

const result = spawnSync(nodeExec, eslintArgs, {
  cwd,
  stdio: 'inherit',
})

if (result.error) {
  throw result.error
}

process.exit(result.status ?? 1)
