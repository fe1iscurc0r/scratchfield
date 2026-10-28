'use strict';

/**
 * 变异对照（不修改源码）：复刻修复前桥的形态——把纯 payload 包成 preload 世界的
 * `MessageEvent` / `CloseEvent` 再交给页面。
 *
 * 用途：证明工装能抓住「Event 实例过不了 contextBridge」这个回归。
 * 预期红：`回显内容正确` 失败（页面拿到的是克隆后的空对象），退出码 1。
 *
 *   electron tests/runtime/bridge-e2e.main.js \
 *     --mode bridge --isolation true \
 *     --preload tests/runtime/bridge-e2e.preload-legacy-event.js
 */

const { contextBridge, ipcRenderer } = require('electron');

const { createWebSocketBridge } = require('../../src/websocket-bridge');
const { WS_PROXY_CHANNELS } = require('../../src/ipc-channels');

const real = createWebSocketBridge({ ipc: ipcRenderer, channels: WS_PROXY_CHANNELS });

const legacy = {
  ...real,
  create(url, protocols) {
    const handle = real.create(url, protocols);
    return {
      ...handle,
      addEventListener(type, fn) {
        handle.addEventListener(type, (payload) => {
          if (type === 'message') {
            fn(new MessageEvent('message', { data: payload }));
          } else if (type === 'close') {
            fn(new CloseEvent('close', {
              code: payload && payload.code,
              reason: payload && payload.reason,
            }));
          } else {
            fn(payload);
          }
        });
      },
    };
  },
};

contextBridge.exposeInMainWorld('nekoWebSocket', legacy);
