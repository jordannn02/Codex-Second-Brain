# Second Brain 最新用法

更新日期：2026-11-03。本文整理目前個人工作流的使用方式；公開倉庫提供可執行的參考 CLI、規格與合成示例，不包含私人知識庫、帳號、會議原文或本機服務設定。

## 最快開始：直接說你要做什麼

| 目的 | 可以直接說 | 預期行為與邊界 |
|---|---|---|
| 接續專案 | 「先讀第二大腦相關索引，整理上次進度與下一步」 | 讀最小必要上下文，指出來源與待驗證事項；不自動保存。 |
| 查找舊知識 | 「找我之前關於某個主題的決策與依據」或 `/obsidian-find` | 索引導向相關筆記，再讀原始證據；歷史結論不等於現況。 |
| 完成工作 | 「依既有決策幫我處理這件事」 | 選適合的工具，查證，先交付可用結果。 |
| 保存本次成果 | 「存一下」或 `/obsidian-save` | 最多一個長期保存目標；優先窄幅更新既有筆記。 |
| 留下可重用規則 | 「這件事下次要記得」 | 一個目標，包含 Trigger / Rule / Scope / Evidence / Exception。 |
| 回顧但不保存 | 「檢討這次試錯，先不要保存」 | 提供分析；檢討本身不授權寫入。 |
| 維護知識庫 | 「檢查健康狀態，先列出問題」或 `/obsidian-health` | 先報告，修正與破壞性處理依實際授權範圍執行。 |
| 了解目前狀態 | `/obsidian-world`、`/obsidian-projects`、`/obsidian-recap` | 依已安裝的命令檔讀取上下文，不保證所有服務已連接。 |

這些 slash commands 是完整 vault 的 agent 指令路由，不是公開 CLI 子命令。必須先有相應 `.codex/commands/<name>.md` 與所需工具；只 clone 本倉庫不會安裝完整個人環境。舊命令若描述自動寫入、PINNED、Daily 或 backlinks，仍須遵守目前的明確授權與最小寫入規則。

## 平常怎麼運作

```text
使用者提出任務
  → 判斷是否需要既有知識
  → 讀最小上下文與相關來源
  → 有相關路由記憶時，先查建議與失敗紀錄
  → 執行任務、驗證證據、交付結果
  → 沒有保存要求：結束
  → 有保存／既有維護授權：規劃目標 → 檢查 → 最小寫入 → 驗證與讀回
```

簡單問題直接處理，不為了流程而讀完整 vault。需要歷史脈絡時，從 `_CLAUDE.md` 的規則與 `index.md` 的導航開始；`Home.md` 是目前工作入口，`CRITICAL_FACTS.md` 保持精簡。再按任務讀專案、決策、來源或證據，不把所有筆記塞入每次對話。Agent 應簡短說明已讀哪些起始上下文，或未讀的原因。

## 保存與維護是兩種不同授權

- 一般對話不自動保存。完成工作、有用洞見、使用者糾正、失敗或成功都不是寫入授權。
- 「存一下」保存當前工作，最多一個長期目標；不順便更新索引、Daily、看板、日誌、backlinks 或 Memory Graph。
- 「下次要記得」才是可重用規則保存；一般規則筆記不等於修改全域 `AGENTS.md`、技能或 vault 規則。
- 明確的多檔維護可涵蓋有界目標；完整個人 vault 每份 Capture Gate manifest 最多五個目標。不用週維護模式繞過一般保存限制。
- 已授權排程在其保存範圍內持續運作；不必每次重新要求相同授權，也不能據此擴張到刪除、封存、合併或覆寫證據。
- 敏感與生產資料需有相應授權；密碼、token、私鑰等秘密永不寫入。

完整個人 vault 若安裝 `.codex/scripts/capture_gate.py`，先列出相對 Markdown 目標，以 `EXPLICIT_COMMAND` 或符合授權的 `WEEKLY_CONSOLIDATION` 做 dry-run。只有 `allowed: true` 才能寫入 `manifest.proposed_changes`，接著執行 manifest 要求的 schema validation 並讀回原目標。Gate 驗證目標，不會替使用者授權。公開版的 JSONL capture 與個人 vault 的 Markdown Capture Gate 是不同介面。

新增長期筆記遵守 vault 的 AI-first 格式：`type`、`date`、`tags`、`ai-first: true`，`## For future Claude`、相關 wikilinks、來源、日期與必要的信心標記。既有筆記只做必要更新，避免為了格式整理重寫歷史。

## 查證：記憶幫你找路，來源支持結論

| 層級 | 能支持什麼 |
|---|---|
| 索引、筆記與 Memory Graph | 歷史背景、已作決策、可能路徑。 |
| 會議紀錄、文件、規格 | 討論、需求與設計意圖。 |
| 原始碼、schema、測試 | 實作邏輯及測試範圍內的行為。 |
| 目前 runtime、資料查詢、UI | 指定環境與時間下的實際狀態。 |
| 寫入授權 | 允許執行的動作與範圍，與技術可達性分開確認。 |

報告分清 `configured`（已設定）、`visible`（能看到）、`executed`（已執行）、`verified-working`（驗證成功）。舊筆記或會議紀錄不能直接證明當前系統已實作、正式上線或通過驗收。

## Memory Graph 怎麼用

有相關歷史時先做路由 preflight，利用 `preferred_tool_for`、`state_action_edge`、`workflow_shortcut` 等建議；`avoid_if`、`suppress` 降低已知失敗路徑的優先序。重試已知失敗前，使用完整環境提供的 attempt guard。這些建議不擴張權限，也不能取代目前來源驗證。

個人版 `memory_graph_cli.py` 的 `preflight`、`attempt-guard`、`record-attempt`、`record-session` 不是本倉庫參考 CLI 的同名功能。其中 `record-attempt`、`record-session`、`self-correct` 都涉及持久化學習，需明確保存或既有維護授權；讀取路由不表示允許寫入回饋。

## 公開參考版：可立即執行的指令

在 repository 根目錄執行：

```bash
python3 -m codex_second_brain.cli --help
python3 -m codex_second_brain.cli validate demo-vault
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
python3 -m codex_second_brain.cli route-suggest demo-vault "debugging noisy search source trace"
python3 -m codex_second_brain.cli explain-edge demo-vault edge_debugging_graph_first_after_noisy_search
```

需要建立新 vault 時才執行（會建立檔案）：

```bash
python3 -m codex_second_brain.cli init ./my-vault
```

預覽 capture，不落盤：

```bash
python3 -m codex_second_brain.cli capture \
  --vault demo-vault \
  --type route-worked \
  --summary "Verified route completed the sample task" \
  --evidence "demo-vault/fixtures/memory-graph.jsonl"
```

`capture`、`record-outcome`、`self-correct`、`decay`、`ingest-momo-route` 預設 dry-run；只有保存範圍已授權才加 `--write`。尤其 `ingest-momo-route --write` 同時涉及 capture 與 graph，不能拿單篇筆記的保存授權套用。`consolidate --dry-run` 產生候選報告，不代表自動整理完成。

## 會議、跨機與工具整合

完整個人環境可將會議來源、逐字稿、視覺證據及摘要保留為各自可追溯的證據，再用筆記串聯。不同來源保留各自識別與時間；去重、水位、附件、遠端同步與本機保存各自驗證。看到摘要不等於完整影音已備份。這些連接器、排程與雲端設定不由公開參考 CLI 自動提供。

跨機共享工作交接時，記錄 repository、分支、commit、未提交變更、已完成事項、測試、阻礙與下一步。程式碼用各機獨立 checkout 與 Git；筆記傳輸不提供鎖定或合併保證，避免兩台同時寫同一檔。不要同步整個 agent 執行狀態、sessions、SQLite/WAL、快取或認證。同步成功與可還原備份是不同驗證。

工具選擇以任務、資料型態與目前可用能力為準；使用者明確指定的工具優先。獨立且有界的工作可在適用授權下交給 sub-agent，主 agent 負責整合與驗收。特定模型、GUI 路由、連接器與權限是本機設定，不是本倉庫保證。

## 維護與驗證範圍

本次更新是操作文件對齊，不宣稱重新驗收完整個人環境。健康檢查、檢索評估、schema、graph、快照與還原應分別保留證據；歷史成功不保證現在仍有效。排程設定、實際執行與結果讀回也應分開報告。

公開發布只包含方法、文件、schema 與合成示例。不要把私人 vault 根目錄直接當發布來源。只從 public-safe package 或其獨立 checkout 提交明確檔案。

相關文件：[Capture Routing](../system/capture-routing.md)、[Agent Instructions](../system/AGENTS.example.md)、[Dry-Run Automation](dry-run-automation.md)、[momo-tools Integration](momo-tools-integration.md)、[Security](../SECURITY.md)。

本文依 2026-11-03 讀取的本機操作規則、保存命令、上下文命令與公開 CLI 整理；本機私人來源不隨文件公開。規則與介面若更新，應以目前安裝版本與當前授權為準。
