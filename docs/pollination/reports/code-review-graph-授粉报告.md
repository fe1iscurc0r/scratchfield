# code-review-graph 鎺堢矇鎶ュ憡

> 2026-08-29 路 娌堥仴绾垮畬鎴?路 鏉ユ簮锛歵irth8205/code-review-graph锛圡IT锛?0.9K鈽咃紝MCP鍏煎锛孋I闆嗘垚锛?> clone 鍦?github_haul/code-review-graph/
> 瀵瑰簲锛欱atch-1B 鎵揣鏃ユ姤"code-review-graph锛?0970鈽咃紝浠ｇ爜鐭ヨ瘑鍥捐氨鈫掓潗鏂欑煡璇嗗簱瀹炰綋鍏崇郴锛?

## 涓€鍙ヨ瘽

浠ｇ爜瀹℃煡鐭ヨ瘑鍥捐氨锛歵ree-sitter AST 鍏ㄩ噺瑙ｆ瀽浠ｇ爜缁撴瀯锛屽閲忚窡韪彉鏇达紝MCP 鍗忚娉ㄥ叆绮剧‘涓婁笅鏂囩粰 AI coding 宸ュ叿锛孭R 鑷姩璇勯闄╁垎/鍙楀奖鍝嶆墽琛屾祦/娴嬭瘯缂哄彛銆?1x token 缂╁噺锛坒lask 鍏ㄩ噺璇?143594 tokens 鈫?鍥炬煡璇?2196 tokens锛夈€侰I/CD 鍘熺敓闆嗘垚锛屾瘡鏉?PR 鑷姩鍙戜竴鏉?sticky comment 骞舵寔缁洿鏂般€?
## 鍏抽敭鏁版嵁

| 鎸囨爣 | 鍊?|
|------|-----|
| token 缂╁噺 | 71x锛坒lask corpus 瀹炴祴锛墊
| 鏀寔骞冲彴 | 15+锛圕laude Code/Codex/Cursor/Windsurf/Zed/Continue/OpenCode/Antigravity/Gemini CLI/Qwen/Qoder/Kiro/GitHub Copilot绛夛級|
| PR 璇勮 | 鍗曟潯 sticky comment锛岄闄╁垎+鎵ц娴?娴嬭瘯缂哄彛锛屾寔缁洿鏂?|
| CI 妯″紡 | GitHub Action锛屽叏绋嬫湰鍦拌繍琛岋紝涓嶄笂浼犳簮鐮?|
| 澧為噺璺熻釜 | 浠ｇ爜鍙樺寲鍚庡閲忛噸寤哄浘锛屼笉鍏ㄩ噺閲嶈窇 |
| 璁稿彲 | MIT 鉁咃紙鍙悶 AGPL 涓讳粨锛墊
| MCP | 鍘熺敓鏀寔锛圡CP server + stdio锛墊

## 鏋舵瀯锛堜粠婧愮爜鎺ㄦ柇锛?
```
code_review_graph/
  core/          # tree-sitter AST 瑙ｆ瀽锛屼唬鐮佺粨鏋勬彁鍙?  graph/         # 鍥炬瀯寤猴紙nodes = 鍑芥暟/绫?鍙橀噺锛宔dges = 璋冪敤/瀵煎叆/寮曠敤锛?  mcp/           # MCP server 瀹炵幇锛坰tdio锛?  github_action/ # GitHub Action workflow
  cli/           # 鍛戒护琛屽伐鍏凤紙build/install/analyze锛?```

- **瑙ｆ瀽**锛歵ree-sitter锛堢‘瀹氭€э紝鏈湴锛岄浂 LLM 璋冪敤锛?- **鍥捐妭鐐?*锛氬嚱鏁板畾涔夈€佺被瀹氫箟銆佸叏灞€鍙橀噺銆佸鍏ヨ鍙?- **鍥捐竟**锛氳皟鐢ㄥ叧绯伙紙calls锛夈€佸鍏ュ叧绯伙紙imports锛夈€佸紩鐢ㄥ叧绯伙紙references锛?- **PR 璇勯闄╁垎**锛氬熀浜庡浘鐨勮繛閫氭€?鍙樻洿棰戠巼+娴嬭瘯瑕嗙洊缂哄彛

## 瀵?Lumo 鐨勬帴鍏ヤ环鍊?
1. **浠ｇ爜瀹℃煡**锛歴cratchpad/apiserver/ + summer_memory/ 鎺ュ叆 鈫?AI 浠ｇ爜瀹℃煡鑳藉姏
2. **MCP serve**锛歝ode-review-graph MCP server 鈫?娉ㄥ唽杩?mcpserver 鈫?Lumo agent 鍙煡璇唬鐮佸浘
3. **token 缂╁噺**锛氭壒閲忎唬鐮佸垎鏋愶紙apiserver/agentic_tool_loop.py 绛夊ぇ鏂囦欢锛夆啋 鍥炬煡璇唬鏇垮叏閲忚锛岃妭鐪佷笂涓嬫枃
4. **CI 闆嗘垚**锛氬ぉ閫?璺?GitHub Action 鈫?PR 鑷姩瀹℃煡锛堥厤鍚?GitHub token锛?5. **涓?graphify 浜掕ˉ**锛歡raphify = 鍏ㄤ唬鐮佸簱鍙煡璇㈢煡璇嗗浘璋憋紙閫氱敤锛夛紝code-review-graph = 瀹℃煡涓撶敤锛圥R 椋庨櫓鍒?娴嬭瘯缂哄彛锛?
## 涓嶉噸鍙犵‘璁?
- graphify锛?3.5k鈽咃級锛氶€氱敤浠ｇ爜/鏂囨。鍥捐氨锛岄€傜敤鎺㈢储鎬ф煡璇?- code-review-graph锛?0.9k鈽咃級锛氬鏌ヤ笓鐢紝CI 鍘熺敓锛岄闄╁垎+鍙樻洿褰卞搷+娴嬭瘯缂哄彛
- 涓よ€呭彲鍙犲姞锛歡raphify 寤哄叏閲忓浘锛宑ode-review-graph 鍋氬閲?PR 鍒嗘瀽

## 钀藉湴寤鸿

- **P0**锛氭湰鍦?install + `code-review-graph build` 璺?apiserver/ 鈫?璇勪及 token 缂╁噺鏁堟灉
- **P0**锛歁CP serve 鈫?娉ㄥ唽杩?mcpserver锛堜笌 fault_inject 鍚岀骇锛?- **P1**锛欸itHub Action 鎺ュ叆澶╅€? 鈫?PR 鑷姩瀹℃煡 workflow
- **P2**锛氫笌 graphify 鍙犲姞锛歅R 瑙﹀彂 code-review-graph 瀹℃煡 + 鏃ュ父鏌ヨ璧?graphify


---


## 附录：源码实读勘察（02 线）


# code-review-graph 鎺堢矇鎶ュ憡锛堝嫎瀵熺粨璁猴級

> 鐘舵€侊細鉁?鍕樺療瀹屾垚锛?026-08-29锛?> **璇氬疄鏍囨敞**锛氬伐鍗曞亣璁炬湰鎶ュ憡涓?`github_haul/code-review-graph/` clone 宸茬敱涓婃父鍕樺療鏅鸿兘浣撲骇鍑猴紱
> 瀹為檯鍏ㄤ粨鎵€鏈夊垎鏀潎鏈壘鍒般€傛湰鎶ュ憡鐢辨櫤鑳戒綋 02 琛ュ仛鍕樺療鍚庢挵鍐欙紝clone 鐢辨湰鏅鸿兘浣?> `git clone --depth 1 https://github.com/tirth8205/code-review-graph` 鐢熸垚锛?026-08-29锛孒EAD b5866875锛夈€?> 缁撹鍧囦负鏈満婧愮爜瀹炶锛岄潪杞堪銆?
## 涓€銆佷笂娓告鍐?
| 椤?| 缁撹 |
|---|---|
| 浠撳簱 | https://github.com/tirth8205/code-review-graph |
| License | **MIT**锛圕opyright (c) 2026 Tirth Kanani锛夆啋 鍙悶鍏?AGPL 涓讳粨锛岄渶淇濈暀 license 澹版槑锛堝凡闅忔帴鍏ュ眰闄?`UPSTREAM-LICENSE`锛?|
| 瀹氫綅 | 瀹℃煡涓撶敤浠ｇ爜鐭ヨ瘑鍥捐氨锛歵ree-sitter AST 瑙ｆ瀽 鈫?鍥炬瀯寤?鈫?MCP server锛坰tdio/HTTP锛? CLI |
| MCP 鍏ュ彛 | `code_review_graph/main.py`锛孎astMCP锛宍code-review-graph serve`锛岀害 30 涓?`@mcp.tool()` |
| 鏍稿績宸ュ叿 | detect_changes / get_impact_radius / query_graph / get_architecture_overview / build_or_update_graph 绛?|
| 渚濊禆 | mcp銆乫astmcp銆乼ree-sitter銆乼ree-sitter-language-pack銆乸yyaml銆乶etworkx銆亀atchdog 鈥斺€?**閲?* |
| 浣撻噺 | 浠?`parser.py` 灏?16K 琛岋紙澶氳瑷€鏀寔锛夛紝`graph.py` 2.3K 琛?|

## 浜屻€佹帴鍏ュ喅绛栵紙瀵圭収閬垮潙閾佸緥锛?
1. **涓嶆暣鍖呭紩鍏?*锛氫笂娓?fastmcp/networkx/watchdog 鍏ㄥ妗惰繚鑳?涓嶅紩閲嶄緷璧?閾佸緥銆?   鍙傜収 graphify 鍏堜緥锛坄mcpserver/adapters/graphify/`锛歟ngine.py 鑷缓钖勫紩鎿?+ adapter.py Bridge + agent-manifest.json锛夛紝
   鑷缓纭畾鎬ц杽寮曟搸锛岃涔夊榻愪笂娓?4 涓牳蹇冨伐鍏凤紝浠呰鐩栫洰鏍囧満鏅紙**Python 婧愮爜瀹℃煡**锛夈€?2. **渚濊禆棰勭畻**锛氱洰鏍囨枃浠讹紙apiserver/銆乻ummer_memory/锛夊叏涓?Python锛宻tdlib `ast` 瀹屽叏澶熺敤涓旈浂鏂颁緷璧栥€?   鍏ㄧ‘瀹氭€р€斺€旀瘮閾佸緥鍏佽鐨?tree-sitter 鍞竴蹇呰鏂颁緷璧?鏇寸渷锛?*瀹為檯闆舵柊渚濊禆**锛夈€倀ree-sitter 鐣欎綔灏嗘潵
   澶氳瑷€锛?ts/.go 绛夛級鎵╁睍鏃剁殑鍙€夊寮猴紝鎺ュ叆灞傜暀鏈?parser 鎵╁睍浣嶃€?3. **涓?graphify 鍒嗗伐**锛堜簰琛ヤ笉閲嶅彔锛夛細
   - graphify = 閫氱敤鐭ヨ瘑鍥捐氨锛堜唬鐮?鏂囩尞/PDF 鈫?GraphRAG 妫€绱紝EXTRACTED/INFERRED 缃俊杈癸級
   - code-review-graph = 瀹℃煡涓撶敤锛坓it diff 鈫?鍙樻洿鍑芥暟 鈫?椋庨櫓鍒?+ 娴嬭瘯缂哄彛 + 褰卞搷鍗婂緞 + 鍙楀奖鍝嶆墽琛屾祦锛?4. **token 缂╁噺**锛氫笂娓稿疄娴嬪彛寰?71x锛堝叏閲忚 143594 tokens 鈫?鍥炬煡璇?2196 tokens锛夈€傛湰浠?apiserver/
   瀹炴祴瑙?`mcpserver/adapters/code_review/README.md`锛堝惈澶嶇幇鍛戒护锛屼及绠楀彛寰?chars/4 涓庝笂娓?   `context_savings.CHARS_PER_TOKEN` 涓€鑷达紝濡傚疄鏍囨敞涓轰及绠楄€岄潪 tokenizer 绮剧‘鍊硷級銆?5. **涓婃父椋庨櫓鍒?娴嬭瘯缂哄彛璁捐鍙傜収**锛歚tools/review.py` 椋庨櫓鎺掑簭 + 娴嬭瘯缂哄彛銆乣changes.py` diff鈫掑嚱鏁版槧灏勩€?   褰卞搷鍗婂緞 BFS銆傛湰寮曟搸涓鸿璁″弬鐓х骇鑷爺瀹炵幇锛堝叕寮忕畝鍖栧苟鍦ㄤ唬鐮佸唴鏂囨。鍖栵級锛岄潪閫愯缈昏瘧銆?
## 涓夈€乵cpserver 鎺ュ叆鎯緥鏍稿锛圫PEC-16 + 鏃㈡湁 adapter锛?
- 娉ㄥ唽浜岄€氶亾锛氣憼 `mcpserver/adapters/__init__.py` `_ADAPTERS` 涓変欢濂?Protocol 鍨嬶紙CAPABILITY/healthcheck/register锛岄粯璁ゅ紑锛夛紱
  鈶?**manifest 鍨?*锛坄agent-manifest.json` + Bridge 绫?+ `handle_handoff`锛宍mcp_registry.scan_and_register_mcp_agents`
  鑷姩娉ㄥ唽锛夆€斺€攇raphify/hamlog 璧版閫氶亾銆傛湰鎺ュ叆璧?**鈶?manifest 鍨?*銆?- 妯″潡鍓嶇紑鐧藉悕鍗?`ALLOWED_MODULE_PREFIXES = ["mcpserver.", "vendor."]` 鈫?`mcpserver.adapters.code_review.adapter` 鉁?- 闂ㄧ锛氬伐鍗曡姹?`ENABLE_ADAPTER_CODE_REVIEW` **榛樿鍏?*锛堝尯鍒簬涓変欢濂楅粯璁ゅ紑锛夈€?  瀹炵幇锛欱ridge `__init__` 鏈樉寮忓紑鍚嵆 raise 鈫?`create_agent_instance` 鎹曡幏 鈫?涓嶆敞鍐?鈫?涓嶇牬鍧忕幇鐘躲€?- SPEC-16 褰掑睘娉ㄨ锛歋PEC-16 鏄啣鐜嬪场璋风嚎锛坈anyon-kb 浠擄級鐨勬€荤翰锛屾湰鎺ュ叆灞炰簬 scratchpad 涓荤嚎
  mcpserver锛屽啣鐜嬪场璋蜂晶灏嗘潵濡傞渶鍙€氳繃 stdio 鎷夎捣鏈ā鍧楀鐢ㄣ€?
## 鍥涖€侀闄╀笌闄愬埗锛堣瘹瀹炴竻鍗曪級

- 钖勫紩鎿?v1 浠呰В鏋?Python锛坰tdlib ast锛夛紱澶氳瑷€寰?tree-sitter 鍙€夊寮恒€?- 椋庨櫓鍒嗕负鍚彂寮忓叕寮忥紙鍙樻洿浣撻噺 + 鎵囧叆/鎵囧嚭 + 娴嬭瘯缂哄彛锛夛紝闈炰笂娓稿悓娆炬潈閲嶏紝缁撴灉鍙綔瀹℃煡浼樺厛绾у弬鑰冦€?- 娴嬭瘯缂哄彛鍒ゅ畾鐢?娴嬭瘯鏂囦欢瀛樺湪 + 鎻愬強鍑芥暟鍚?import"鍚彂寮忥紝瀛樺湪婕忓垽/璇垽鍙兘锛屽凡鍦ㄨ緭鍑轰腑鏍囨敞 heuristic銆?- token 瀵规瘮鍙ｅ緞涓?chars/4 浼扮畻锛堜笌涓婃父鍚屽彛寰勶級锛岄潪 tokenizer 绮剧‘璁℃暟锛涙暟鎹 README 骞堕檮澶嶇幇鍛戒护銆?- CI 闆嗘垚锛?2-03锛夊彧鍋氫簡 workflow 鏃ュ織/step summary 鐗堬紝sticky comment 鍗囩骇璺緞宸叉敞閲婅鏄庯紱**灏氭湭鐪熷疄 PR 瀹炴祴**锛岀暀鐢ㄦ埛楠岃瘉銆?
