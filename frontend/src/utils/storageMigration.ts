const STORAGE_KEY_MIGRATIONS: ReadonlyArray<readonly [string, string]> = [
  ['naga-access-token', 'lumo-access-token'],
  ['naga-refresh-token', 'lumo-refresh-token'],
  ['naga-audio-settings', 'lumo-audio-settings'],
  ['naga-bg-owned', 'lumo-bg-owned'],
  ['naga-bg-active', 'lumo-bg-active'],
  ['naga-startup-live2d-source', 'lumo-startup-live2d-source'],
  ['naga-active-tab', 'lumo-active-tab'],
  ['naga-session', 'lumo-session'],
]

export function migrateLegacyStorageKeys(): void {
  try {
    for (const [oldKey, newKey] of STORAGE_KEY_MIGRATIONS) {
      if (localStorage.getItem(newKey) !== null)
        continue
      const oldValue = localStorage.getItem(oldKey)
      if (oldValue === null)
        continue
      localStorage.setItem(newKey, oldValue)
      localStorage.removeItem(oldKey)
    }
  }
  catch { /* localStorage 不可用时静默 */ }
}

migrateLegacyStorageKeys()
