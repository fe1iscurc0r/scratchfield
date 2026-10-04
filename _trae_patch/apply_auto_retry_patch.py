# -*- coding: utf-8 -*-
"""
Trae CN 聊天「上游错误自动重试」补丁
- 把错误码 4028（上游 HTTP 502/503/504 等）加入自动重试白名单
- 重试次数兜底至少 3 次，退避至少 1.5s/次（1.5s → 3s → 4.5s）
- 幂等：已打过补丁则跳过；自动备份原文件
- Trae 更新会覆盖 resources/app，届时重新运行本脚本即可
"""
import shutil
import sys
import time

TARGET = r'D:\Trae CN\resources\app\node_modules\@byted-icube\ai-modules-chat\dist\index.mjs'

# (旧字节串, 新字节串, 说明)
PATCHES = [
    # v2 [ai-chat/v2] ErrorHandler -> ChatSessionService.scheduleAutoRetry
    # 1) 强制启用自动重试 + 4028 永远可重试（不受服务端动态配置影响）
    (b'if(!l?.enable||a||void 0===i||!c.includes(i)||!r)return this.clearAutoRetryState(t),!1;',
     b'if(!1||a||void 0===i||!c.includes(i)&&4028!==i||!r)return this.clearAutoRetryState(t),!1;',
     'v2: 强制启用重试，4028 加入白名单'),
    # 2) 重试次数兜底 >= 3
    (b'let u=Math.max(0,l?.maxRetryCount??1),d=this.autoRetryStates.get(t),p=d?.attempt??0;',
     b'let u=Math.max(3,l?.maxRetryCount??3),d=this.autoRetryStates.get(t),p=d?.attempt??0;',
     'v2: maxRetryCount 兜底 3'),
    # 3) 退避间隔兜底 >= 1.5s（attempt 递增：1.5s/3s/4.5s）
    (b'let f=m.attempt*Math.max(0,l?.baseDelayMs??200);',
     b'let f=m.attempt*Math.max(1500,l?.baseDelayMs??1500);',
     'v2: baseDelayMs 兜底 1.5s'),
    # v1 旧控制器路径（SOLO/agent 等），保持一致
    (b'm=rQ({errorCode:n?.code,retryableErrorCodes:c,enabled:u,retryCount:p,maxRetryCount:d})',
     b'm=rQ({errorCode:n?.code,retryableErrorCodes:[...c,4028],enabled:!0,retryCount:p,maxRetryCount:Math.max(3,d)})',
     'v1: rQ 决策加入 4028、次数兜底 3'),
    (b'if(!(n?.retryableErrorCodes??[-1,3003]).includes(e)||!(n?.enable??!0))return!1;let i=n?.maxRetryCount??1;return(this.autoRetryCountMap.get(t)??0)<i}',
     b'if(![...(n?.retryableErrorCodes??[-1,3003]),4028].includes(e)||!(n?.enable??!0))return!1;let i=Math.max(3,n?.maxRetryCount??3);return(this.autoRetryCountMap.get(t)??0)<i}',
     'v1: shouldAutoRetry 加入 4028、次数兜底 3'),
]


def main() -> int:
    with open(TARGET, 'rb') as f:
        data = f.read()
    print(f'target: {TARGET} ({len(data):,} bytes)')

    changed = 0
    for old, new, desc in PATCHES:
        n_old, n_new = data.count(old), data.count(new)
        if n_new > 0 and n_old == 0:
            print(f'[skip] {desc}: 已打过补丁')
            continue
        if n_old != 1:
            print(f'[FAIL] {desc}: 旧串出现 {n_old} 次（期望 1），为安全起见不改动')
            return 1
        data = data.replace(old, new, 1)
        changed += 1
        print(f'[ok]   {desc}')

    if changed == 0:
        print('全部补丁均已生效，无需写入')
        return 0

    backup = TARGET + f'.bak-{time.strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(TARGET, backup)
    print(f'backup: {backup}')

    with open(TARGET, 'wb') as f:
        f.write(data)
    print(f'written: {len(data):,} bytes, {changed} 处补丁')

    # 回读校验
    with open(TARGET, 'rb') as f:
        check = f.read()
    ok = all(check.count(new) >= 1 and check.count(old) == 0 for old, new, _ in PATCHES)
    print('verify:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
