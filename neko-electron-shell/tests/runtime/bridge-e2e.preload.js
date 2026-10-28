'use strict';

/**
 * 场景 bridge 的 preload：**真文件** websocket-bridge.js + 真通道名，
 * 走生产同一条 `contextBridge.exposeInMainWorld`.
 */

const { ipcRenderer, contextBridge } = require('electron');
const { createWebSocketBridge } = require('../../src/websocket-bridge');
const { WS_PROXY_CHANNELS } = require('../../src/ipc-channels');

const bridge = createWebSocketBridge({
  ipc: ipcRenderer,
  channels: WS_PROXY_CHANNELS,
  log: (msg) => console.log('[bridge-e2e preload] ' + msg),
});

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('nekoWebSocket', bridge);
} else {
  window.nekoWebSocket = bridge;
}
