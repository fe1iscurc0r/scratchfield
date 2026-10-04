/**
 * api 层内部共享依赖（卷191-A2 从 core.ts 顶部拆出）。
 *
 * 这里集中 core.ts 原本在模块顶部做的事：
 *   - 外部类型/工具函数的 re-export（域文件统一从本模块取，避免各自写 import 路径）
 *   - Agent Server (port 8001) 的 axios 实例 agentAxios
 */
import type { TravelSession } from '@/travel/types'
import type { Config } from '@/utils/config'
import type { StreamChunk } from '@/utils/encoding'
import axios from 'axios'
import { aiter } from 'iterator-helper'
import { decodeStreamChunk, readerToMessageStream } from '@/utils/encoding'
import { toCamel, toSnake } from '@/utils/keyCase'
import { ACCESS_TOKEN } from '../index'

export type { Config, StreamChunk, TravelSession }
export { ACCESS_TOKEN, aiter, axios, decodeStreamChunk, readerToMessageStream, toCamel, toSnake }

// Agent Server (port 8001) 的 axios 实例
export const agentAxios = (() => {
  const instance = axios.create({
    baseURL: 'http://localhost:8001',
    timeout: 180 * 1000, // 干员实例操作可能较慢
    headers: { 'Content-Type': 'application/json' },
    transformRequest(data) {
      if (
        data
        && typeof data === 'object'
        && !(data instanceof FormData)
        && !(data instanceof ArrayBuffer)
        && !(data instanceof Blob)
      ) {
        return JSON.stringify(toSnake(data))
      }
      return data
    },
    transformResponse: [(data: string) => {
      try {
        return toCamel(data)
      }
      catch {
        return data
      }
    }],
  })
  instance.interceptors.request.use((config) => {
    if (ACCESS_TOKEN.value) {
      config.headers.Authorization = `Bearer ${ACCESS_TOKEN.value}`
    }
    return config
  })
  instance.interceptors.response.use(response => response.data)
  return instance
})()
