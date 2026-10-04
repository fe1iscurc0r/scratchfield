/**
 * 域方法集合的声明辅助（卷191-A2）。
 *
 * 各域文件用：
 *   export const marketMethods = {
 *     getMarketItems() { return this.instance.get(...) },
 *   } satisfies DomainShape
 *
 * `DomainShape` 通过 `ThisType` 把方法里的 `this` 绑定到宿主上下文
 * （instance / endpoint），同时 `satisfies` 保留对象字面量的精确类型
 * —— 方法名、参数、返回类型全部可被调用方推导。
 *
 * 为什么不用泛型工厂函数：`defineDomain<T>(m: T & ThisType<..>)` 里的 T
 * 会被约束推断退化，调用方拿到索引签名而非具体方法（实测）。
 */
export interface DomainContext {
  instance: import('axios').AxiosInstance
  endpoint: string
}

/**
 * 域方法集合形状。
 *
 * `this` 类型 = DomainContext & 任意方法表（后者供同域内跨方法调用，
 * 如 agents 域 relayAgentMessage → this.streamToAgent）。
 *
 * 注意：方法表的索引签名返回类型必须带 `| undefined` 之外的形态——
 * 用 `(...args: any[]) => any` 直接作为 index signature 会让 TS 认为
 * `this.foo()` 可能是 undefined（noUncheckedIndexedAccess）。
 * 这里改用显式 callable 交叉，保证调用合法。
 */
export type DomainShape = Record<string, (...args: any[]) => any>
  & ThisType<DomainContext & { [K in string]: (...args: any[]) => any }>
  & { [K in string]: (...args: any[]) => any }
