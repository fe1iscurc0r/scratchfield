# 安全债清账报告（2026-10-02）

**清账人**：实验田维护者（用户授权直接执行）｜**仓库**：scratchpad @ main `06968322`

## 一、301条告警来源构成（定性）

| manifest | 条数 | 定性 | 处置 |
|---|---|---|--- |
| NEKO/N.E.K.O/uv.lock | 100 | 上游债 | 不动，等上游修复随同步进来 |
| NEKO plugin-manager package-lock | 103→3 | 上游债 | 合dependabot PR #131/#132/#133 |
| NEKO galgame_plugin training | 17 | 上游债 | 不动 |
| NEKO requirements*.txt | 11 | 上游债 | 不过 |
| NEKO docs | 11→4 | 上游债 | PR已合，余量待重扫 |
/plugin-manager、docs 已大幅下降
| 根 uv.lock | 51 | 自有债 | 本次批量升级已推送，等GitHub重扫 |
| frontend/ | 4→0 | 自有债 | PR #131 已合 |

## 二、本次已做

1. **合3条dependabot PR**（#131 frontend、#132 NEKO docs+plugin-manager 16包、#133 NEKO uv tornado）：301→191，critical 7→6，high 131→75
2. **根uv.lock批量升级**（commit 46f1afdd→06968322）：urllib3 2.6.2→2.8.0、starlette 0.50.0、langsmith 0.14.3、transformers 5.3.0、pygments 2.21.0、orjson 3.12.0、marshmallow 3.24→3.26.2、filelock 3.20→4.0.9、oauthlib 3.3.1→4.0.0、pyasn1 0.6.4、setuptools 84.0.0、python-dotenv 1.2.4、mss 10.2.0 —— **13包升到修复版以上**，`uv sync`验证聊天链路三模块(apiserver.llm_service/intent_router/context_compressor)import正常
3. **litellm死锁存档**：pyproject注释记录根因——apiserver/llm_service.py:19、intent_router.py:17、context_compressor.py:23 模块级import（聊天主链路），不可直接拔。与openai>=3.8.0死锁（litellm全线要求openai<3.0）→ 3 crit+14 high挂账，解法=卷193迁移litellm→openai SDK后拔除
4. 战报落盘 `docs/security-debt-cleanup-2026-10-02.md`

## 三、挂账（不动或不可动）

- **NEKO子树140条**：上游地盘，缓慢修复中，随同步进来
- **chromadb 2crit+2high**：无补丁版本（pre-auth RCE+code injection，主代码926处使用不可移除）——盯上游，出补丁即升
- **litellm 3crit+14high**：待卷193迁移（工单待开）
- 根uv.lock残余：GitHub重扫后复查（升级已进锁，告警应大幅下降）

## 四、验证

- 推送后 `ls-remote` = 本地HEAD = `06968322` ✅
- `.venv` sync后聊天主链路三模块import ok ✅
- GitHub alerts重扫pending，明早复查即知真实残留
