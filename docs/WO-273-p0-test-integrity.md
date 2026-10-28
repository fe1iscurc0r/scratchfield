# WO-273 施工记录 · P0 测试资产：把「绿」变成可验证的绿

- **执行方**：K3（原派 Trae，Trae 已离场后接手）
- **日期**：2026-10-23
- **基线**：`main@ff12ac09ea08`
- **结论**：**T1 收集面已报数并加手动 CI job；T2 / T3 两个假断言已改成真断言，且都做了「改坏 ⇒ FAIL」对照实验。**

---

## §1 T1 · 收集面（P0-14）

### §1.1 五数摘要（实测，非估计）

```
$ python -m pytest NEKO/N.E.K.O/tests -q --collect-only
22843 tests collected, 626 errors in 93.62s
```

| collected | passed | failed | skipped | errors |
|---:|---:|---:|---:|---:|
| **22843** | 0 | 0 | 0 | **626** |

> 收集期 626 个错误 ⇒ **本轮未执行全量**（跑了也只会是"626 个 import 级失败"），
> 按工单兜底条款改为「分类统计 + 失败原因聚类」（下面这节）。

### §1.2 失败原因聚类（626 个错误文件 → 15 个缺失顶层包）

| 缺失包 | 出现次数 | 缺失包 | 出现次数 |
|---|---:|---|---:|
| `soxr` | **348** | `av` | 11 |
| `qrcode` | **106** | `pytest_asyncio` | 7 |
| `portalocker` | **96** | `plugin` | 3 |
| `playwright` | 36 | `cachetools` | 1 |
| `ormsgpack` | 14 | `browser_use` | 1 |
| `msgpack` | 13 | `dashscope` | 1 |
| `scripts` | 11 | `pypdf` | 1 |
| | | `PyInstaller` | 1 |

**判断**：626 个收集错误**全部是环境缺依赖**，没有一条是"测试写错"。前三名（soxr/qrcode/portalocker）
合计 550 次 = **87.9%**。

**实测补充**：本机按需补装 `nest_asyncio / pytest-randomly / pytest-asyncio / cachetools / soxr / qrcode / portalocker`
之后，两个目标文件从 **42 failed / 8 passed** 变成 **80 passed**（见 §2/§3）——
说明"跑不起来"的主因确实是环境，不是用例本身。

### §1.3 门禁建议（**只描述，不执行**）

- **不要**从 `pyproject.toml` 的 `norecursedirs` 删掉 `"NEKO"`：删了裸 `pytest` 会去扫 22843 个用例，
  收集期就炸（实测 93 s + 626 errors）。
- 已加 `neko-collect` job（`.github/workflows/ci.yml`）：
  **只在 `workflow_dispatch` 手动触发**，只报五数 + 缺失包 Top20，**不设 required check**。
- 已加谓词：`pyproject.toml` 的 `markers` 补 `unit` / `integration`（NEKO 用例已用 `@pytest.mark.unit`）；
  并在 `[tool.pytest.ini_options]` 上方写清 NEKO 子树约定。

---

## §2 T2 · `test_cfa_resilience.py` 的恒真断言（P0-15）

**原版（假绿）**

```python
with patch.dict(os.environ, {'LOCALAPPDATA': 'C:\\Users\\Test\\AppData\\Local'}):
    ...
    assert os.environ.get('LOCALAPPDATA') == 'C:\\Users\\Test\\AppData\\Local'   # ← 恒真
```

`patch.dict` 刚塞进去，紧接着断言它等于塞进去的值；`_get_documents_directory()` **一次都没被调用**
（原注释自认 "We can't fully run ... but we can verify"）。

**改后（真断言，且必须显式要 `real_root_resolution` fixture）**

- ① `_get_standard_data_directory_candidates()` 必须**含**环境变量给的那个路径（测"读没读环境变量"）；
- ② `_get_documents_directory()` 返回的目录必须**真实存在且可写**（测"能不能用"）；
- ③ 另加一条：环境变量指向**不存在的深路径**时，返回目录仍必须存在（测"会不会自己建/回退"）。

> ⚠️ 踩坑记录：`tests/conftest.py` 默认把根解析**整段 stub 掉**（返回隔离根 `neko_test_appdata_*`），
> 不请求 `real_root_resolution` fixture 的话，测的永远是 stub —— **仍属假绿**。这是本次第二大发现。

**实测**：`30 passed`（该文件全绿）。

**「改坏 ⇒ FAIL」对照实验**（真改产品代码，改完逐字节还原）

| 动作 | 结果 |
|---|---|
| 把 `storage_roots.py` 的 `candidates.append(Path(localappdata))` 改成 `Path.home()` | **`1 failed`**（`test_appdata_in_candidates`） |
| 还原后 sha256 前 16 位比对 | **一致**（`41e328151d525406`） |

---

## §3 T3 · `test_recent_compress_backup.py` 的伪造属性（P0-16）

**原版（假绿）**

```python
with patch.object(manager, "_create_engine_for", create=True, return_value=created):
    try:
        manager._ensure_engine_exists(name, expected)
    except OSError as exc:
        pytest.fail(...)
    except Exception:
        pass          # ← 把任何失败都吞掉
assert stale_engine.dispose.call_count == 1
```

- `_create_engine_for` 在 `NEKO/N.E.K.O/memory/` 与 `main_logic/` **grep 0 命中**（只在测试里出现），
  `create=True` 现场伪造了一个不存在的属性 ⇒ 「重建分支」根本没被断言；
- `except Exception: pass` 把失败吞掉 ⇒ 用例只剩一条 dispose 计数。

**真实接缝**：`memory/timeindex.py:663` 的**模块级** `create_engine(connection_string)`。

**改后**

- patch `memory.timeindex.create_engine`（真接缝）+ `_assert_timeindex_writable` / `_ensure_tables_exist_with`
  / `_check_and_migrate_schema`；
- **删掉** `except Exception: pass`；
- 断言**具体行为**：`manager.engines[name] is created`、`db_paths[name] == expected`、
  `stale_engine.dispose.call_count == 1`。

**实测**：该文件 **50 passed**（依赖补齐后全绿）。

**「改坏 ⇒ FAIL」对照实验**

| 动作 | 结果 |
|---|---|
| 把 `timeindex.py` 的 `self.engines[lanlan_name] = engine` 改成 `pass`（跳过注册） | **`1 failed`**（`test_engine_repair_branch_self_heals_after_a_failed_disposal`） |
| 还原后 sha256 前 16 位比对 | **一致**（`be9097bd6c755fde`） |

---

## §4 改动清单

| 文件 | 改动 | 行尾 |
|---|---|---|
| `NEKO/N.E.K.O/tests/unit/test_cfa_resilience.py` | 1 条恒真断言 → 2 条真断言（+补 `from pathlib import Path`） | LF |
| `NEKO/N.E.K.O/tests/unit/test_recent_compress_backup.py` | 伪造属性 patch → 真接缝 patch；删 `except Exception: pass`；断言行为 | LF |
| `pyproject.toml` | 补 `unit`/`integration` marker + NEKO 子树约定注释 | LF |
| `.github/workflows/ci.yml` | 加 `workflow_dispatch` + `neko-collect` job | **CRLF（208/208，裸 LF=0）** |
| `docs/WO-273-p0-test-integrity.md` | 本记录 | LF |

**ci.yml 双重验证**：`yaml.safe_load` 解析通过；`CRLF=208 行=208 裸LF=0`。

---

## §5 验收命令

```bash
# 两个目标文件（本地需补依赖，见 §1.2）
python -m pytest NEKO/N.E.K.O/tests/unit/test_recent_compress_backup.py \
                 NEKO/N.E.K.O/tests/unit/test_cfa_resilience.py -q
# 实测：80 passed

# 收集面五数
python -m pytest NEKO/N.E.K.O/tests -q --collect-only
# 实测：22843 tests collected, 626 errors in 93.62s
```

---

## §6 阻塞 / 待办

| # | 项 | 说明 |
|---|---|---|
| 1 | **全量 NEKO 用例未跑通** | 626 个收集错误来自 15 个缺失包（soxr 348 最多）。补齐依赖后**应该**能大幅收敛，但本轮只在两个目标文件上验证到底（80 passed） |
| 2 | CI 无额度 | 七个 PR 的 check_runs 全 `skipped` ⇒ `neko-collect` 目前只能**手动触发**且无 runner 时不会跑；等计费解封再谈设 required check |
| 3 | 267~272 未合入 | 工单要求"未合入先出基线、合入后再跑一次对比"——**第一半已在本记录 §1.1**（22843/626），第二半等合入 |
| 4 | `docs/full-repo-review-2026-10-21/` 的 P0-14/15/16 处置列回填 | 硬边界要求不动该目录 ⇒ 由所有者回填 |
