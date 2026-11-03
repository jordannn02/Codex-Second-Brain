# 安裝公開可攜執行層

此執行層把公開的 41 份 agent 命令、通用參考規則、gate／schema／健康／檢索／備份等腳本與 memory graph 安裝到你指定的 vault。它來自日常控制面的通用程式與公開改寫模板，排除了私人筆記、真實 graph、帳號與執行狀態。命令內容已調整為可攜、明確授權流程；不是私人環境的逐位元鏡像。

需要 **Python 3.12 以上**及完整 repository checkout。`pip install` 提供參考 CLI；不會把 repository 的 portable runtime 安裝到 vault。以下均在 clone 的 repository 根目錄執行：

```bash
git clone https://github.com/jordannn02/Codex-Second-Brain.git
cd Codex-Second-Brain
python3 bin/install-vault-runtime.py /path/to/new-vault
```

預設只輸出 JSON 計畫，不建立目錄或寫入。檢查 `changes`、`conflicts` 與依賴後，明確套用：

```bash
python3 bin/install-vault-runtime.py /path/to/new-vault --apply
```

安裝器逐檔讀回 SHA-256。相同檔案保持原樣；不同的既有工具檔案會阻擋整批套用，請先比較與自行備份。沒有 `--force`，不會覆寫。既有 `AGENTS.md` 與正式 graph sidecar 特別保留；目的目錄內的 symlink 會被拒絕。這是檔案安裝的安全檢查，並不保證其他程式同時修改檔案時的全樹交易隔離；避免並行寫同一 vault。

新 vault 缺少 `AGENTS.md` 時會建立公開命令路由。既有 AGENTS 會保留，請檢閱後在自己的規則加入「相關任務請讀 `.codex/AGENTS.runtime.md`」。安裝器不建立 `_CLAUDE.md`、`index.md`、`Home.md` 或 `CRITICAL_FACTS.md`；需要最小 startup 文件時，另在已授權的新目錄執行：

```bash
python3 -m codex_second_brain.cli init /path/to/new-vault
```

不要用 `--force` 重建已有筆記。它不是搬移私人知識庫或部署雲端服務。

## 安裝位置與依賴

| 內容 | 目的位置 | 依賴／限制 |
|---|---|---|
| 41 份命令及參考模板 | `.codex/commands/`、`.codex/references/` | agent 必須讀取路由及命令；不是 CLI 子命令，也不自動安裝技能 |
| 通用腳本及合成 policy/fixtures | `.codex/scripts/`（含 `scripts/fixtures/` fallback policy）、可選 `.codex/fixtures/` | Python；schema、部分 export 工具另需可選 PyYAML |
| Memory graph CLI、shadow runtime | `Knowledge/Codex/memory_graph/` | 空正式 sidecar 位於 `Knowledge/Codex/memory_graph_edges.jsonl`；既有 sidecar 不覆寫 |
| 公開路由與第三方授權 | `.codex/AGENTS.runtime.md`、`.codex/THIRD_PARTY.md`、`.codex/LICENSE.upstream` | 新 vault 才建立 root AGENTS；保留 MIT 原始聲明 |

若要使用 PyYAML，請在自己選定的虛擬環境明確安裝 `pip install PyYAML`；安裝器不安裝套件。模型搜尋另需 numpy、torch、sentence-transformers 及已取得的本地 Qwen3-Embedding-0.6B 權重。雲端來源、會議／郵件／日曆／Telegram／X／影片與 grounded-research 服務皆需使用者另行設定授權工具；未提供 provider 連線、bot、帳號、排程或 API keys。

上游多平台 build pipeline、Telegram intake、雲端研究腳本及外部 `session-retro` 技能不包含在此分發；命令遇到它們時會使用可用工具或明確回報限制，不能宣稱已執行。可攜命令不引用這些缺失 helper 作為必跑步驟。

## 在目標 vault 驗證

以下命令在**目標 vault 根目錄**執行；`--edges` 是 graph CLI 的全域參數，放在子命令前。

```bash
python3 .codex/scripts/vault_health.py --help
python3 .codex/scripts/capture_gate.py --path . --mode EXPLICIT_COMMAND --target "Knowledge/Example.md" --dry-run --json
python3 Knowledge/Codex/memory_graph/memory_graph_cli.py --edges Knowledge/Codex/memory_graph_edges.jsonl preflight "inspect project context" --json
python3 .codex/scripts/qwen3_search.py --path . --scope core search "project" --json
```

空 vault 可能回報缺少 startup/schema/筆記；這表示工具執行得到診斷，不表示完整環境健康。普通保存是一目標，明確多檔維護使用 `EXPLICIT_MAINTENANCE`（每份 manifest 最多五目標）。`AUTO_CAPTURE` 不允許。gate 並非寫入授權；必須依回傳 manifest 執行必要的 post-write schema 驗證及讀回。

## 選用本機語義搜尋

預設 `--backend lexical`，標準函式庫詞彙搜尋可獨立使用，支援中文。core 與 knowledge 分開回傳；lexical／semantic 分數不合併。搜尋不建立索引、不下載／啟動模型服務、不自動切換虛擬環境。

只有你已另外準備可用的本地模型、Python 依賴與索引時，明確選擇 Qwen backend：

```bash
python3 .codex/scripts/qwen3_search.py --path . --scope core --backend qwen3 search "如何接續專案" --semantic-mode auto --json
```

`semantic.status=ok` 才表示語義推論成功；`skipped` 表示 backend/routing 未啟用；`unavailable` 表示模型、依賴或索引不可用，仍保留 lexical 結果。`routing_decision.semantic_called` 只在實際呼叫模型 encode 時為 true。

索引存於外部 runtime 目錄（預設 `~/.local/share/codex-second-brain/qwen3-search`），包含向量與路徑／offset；這些同樣可能透露私人資訊，不能當公開資料。不同 vault 請使用各自 `--home`，避免 scope 索引互相取代。建立／更新索引會寫檔，需要明確指令與 `--apply`：

```bash
python3 .codex/scripts/qwen3_search.py --path . --home /path/to/local-search-runtime --scope core --backend qwen3 index --apply --json
```

本地索引屬使用者指定的搜尋執行狀態，不等於授權新增筆記、graph feedback 或保存對話。讀取搜尋結果後不會自動更新任何上述資料。
