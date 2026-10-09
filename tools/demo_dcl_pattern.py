"""工单222 任务一 · 嫌疑2 对照演示：裸 check-then-set vs DCL（注入构造延迟放大窗口）。

说明：本脚本演示的是**模式**本身的竞态（不是某个具体站点的实测）——
真实站点构造太快时 GIL 会掩盖竞态，故用 5ms 延迟等价于"构造涉及读文件/建连接"的情形。
"""
import threading
import time

DELAY = 0.005
THREADS = 16


def demo_bare():
    holder = {}
    builds = []

    def ctor():
        time.sleep(DELAY)          # 构造耗时（真实站点：读文件/建连接）
        builds.append(1)
        return object()

    def get():
        v = holder.get("x")
        if v is None:              # check
            v = ctor()             # then set（非原子）
            holder["x"] = v
        return v

    barrier = threading.Barrier(THREADS)
    out = []

    def worker():
        barrier.wait()
        out.append(id(get()))

    ts = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return len(builds), len(set(out))


def demo_dcl():
    holder = {}
    builds = []
    lock = threading.Lock()

    def ctor():
        time.sleep(DELAY)
        builds.append(1)
        return object()

    def get():
        v = holder.get("x")
        if v is None:
            with lock:
                if holder.get("x") is None:
                    holder["x"] = ctor()
        return holder["x"]

    barrier = threading.Barrier(THREADS)
    out = []

    def worker():
        barrier.wait()
        out.append(id(get()))

    ts = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return len(builds), len(set(out))


if __name__ == "__main__":
    for name, fn in (("裸 check-then-set", demo_bare), ("DCL（加锁后）", demo_dcl)):
        rounds = [fn() for _ in range(5)]
        builds = [b for b, _ in rounds]
        print(f"{name:<18} 构造次数（5 轮，每轮 {THREADS} 线程）: {builds} "
              f"→ 双建轮次 {sum(1 for b in builds if b > 1)}/5")
