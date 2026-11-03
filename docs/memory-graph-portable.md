# 可攜式 Memory Graph

`system/vault-runtime/memory_graph/` 提供獨立 Python 3 標準函式庫 CLI，不含私人圖譜、事件或金鑰。它是 advisory routing，不代替目前來源、執行環境或授權的驗證；中文分詞使用 2–4 字 n-gram。以自己的 JSONL sidecar 執行，資料可參考 `demo-vault/fixtures/memory-graph.jsonl` 的合成範例。

```sh
python3 system/vault-runtime/memory_graph/memory_graph_cli.py \
  --edges demo-vault/fixtures/memory-graph.jsonl preflight '會議記錄證據鏈' --json
```

支援 `route`、`preflight`、`attempt-guard`、`explain`、`gaps`、`evidence-chain`、`visualize`；`--help` 列出完整參數。不存在的 sidecar 視為空圖譜；查詢不會建立檔案。不同 relation、權重與 suppressed 狀態影響排序，結果並非事實認證。

## 寫入邊界

`record-use`、`record-attempt`、`record-session`、`self-correct`、`decay`、非 `--dry-run` 的 `maintenance` 都會寫入明確指定的 `--edges`。**只有使用者明確授權保存，或既有維護流程涵蓋這次操作時**，才傳全域選項 `--authorize-write`。成功、失敗、完成任務或 `preflight` 結果都不構成保存授權；CLI 的旗標是操作確認，不是權限系統，呼叫者仍負責判斷授權。執行記錄會建立同目錄 `.lock` 並原子替換 sidecar；多程序鎖使用 Unix `fcntl`。

## Shadow 評估

`shadow-observe`、`shadow-feedback`、`shadow-report`、`shadow-maintenance` 為 counterfactual 評估，不自動注入結果或修改 edges。每一項都需要明確 `--shadow-db` 和 `--authorize-write`；即使 report 也可能初始化 SQLite 和產生 HMAC key。例：

```sh
python3 system/vault-runtime/memory_graph/memory_graph_cli.py \
  --edges /tmp/example-edges.jsonl --shadow-db /tmp/example-shadow.db --authorize-write \
  shadow-observe '會議記錄證據鏈' --profile demo --json
```

Store 不保存原始查詢，使用本地隨機 key 生成摘要，並保存受限錨點與候選資訊；錨點仍可能透露主題或識別字串，不是匿名化保證。SQLite、key 及 WAL 等檔案應放受保護的位置，不要上傳。`shadow-maintenance` 預設只預覽；`--apply` 會清除過期事件。系統的 allowlist 與投影只是有限啟發式，不是通用隱私過濾器。
