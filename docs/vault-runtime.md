# 可攜式 Vault Runtime

這組獨立工具來自 vault runtime，使用者須自行指定 vault、政策與資料；不包含私人筆記、benchmark 案例、營運收據或預設自動排程。所有範例的 `$VAULT` 是使用者指定的路徑，請先以測試 vault 練習。此 runtime 需要 Python 3.12 以上；`export_okf.py` 額外需要 PyYAML（`python3 -m pip install PyYAML`）。`automation_provenance.py` 使用 Unix `fcntl`；兩個 materialize 工具的 `--apply` 需要 macOS 的 `brctl`。其餘工具主要使用 Python 標準函式庫。Python 套件安裝不會自動部署這些檔案。

## 安裝

將 `system/vault-runtime/scripts/` 中的 Python 檔案複製至目標 vault 的 `.codex/scripts/`；將 `scripts/fixtures/ai_first_schema_policy.json` 複製至 `.codex/scripts/fixtures/`。若目標 vault 需要覆寫 schema 政策，可另提供 `.codex/fixtures/ai_first_schema_policy.json`；執行前檢查是否已有同名檔案，避免覆蓋自訂內容。部分產生的驗證指令固定使用 `.codex/scripts/capture_gate.py`，所以若選擇其他安裝位置，必須自行調整命令。工具執行需要使用者自己的 vault 路徑及授權。

## 保存閘門

```sh
python3 "$VAULT/.codex/scripts/capture_gate.py" --path "$VAULT" --mode EXPLICIT_COMMAND --target 'Notes/example.md' --dry-run --json
```

`AUTO_CAPTURE` 一律拒絕；一般 `EXPLICIT_COMMAND` 上限 1，明確授權的多檔維護使用 `EXPLICIT_MAINTENANCE`，每個 manifest 至多 5。`WEEKLY_CONSOLIDATION` 保留既有排程介面，僅適用已授權的維護流程。`allowed: true` 只表示目標通過檢查，**不授權寫入**。僅寫入 `manifest.proposed_changes`，寫後執行 manifest 的 `post_write_schema_validation.command` 並讀回目標；新檔不得有 schema blocker，既有檔不得新增 blocker。token 是未簽章的驗證資料，應保存在可信的本機工作流程，不是安全憑證。OKF 在 vault 內輸出要求精確的 manifest，超過一筆須使用明確的維護模式。

## 常用工具

- `vault_health.py --path "$VAULT" --scope core --json`：唯讀檢查；`--list-scopes` 查看範圍。
- `ai_first_schema_audit.py --path "$VAULT" --policy "$VAULT/.codex/scripts/fixtures/ai_first_schema_policy.json" --scope core --json`：檢查 schema；可以用 `--target` 指定檔案。
- `privacy_gate.py`：需要使用者提供 contexts、角色、路徑與內容掃描規則；自訂規則和掃描結果不代表可公開或完全無敏感資料。
- `vault_status_manifest.py`、`vault_status_watchdog.py`、`retrieval_benchmark.py`、`retention_audit.py`：須自行提供案例、政策、狀態或 ledger；未附個人資料或預設測試案例。狀態檔和 provenance 寫入屬於可持久化動作，須明確授權。
- `vault_stats.py --vault "$VAULT" --print-only`、`index_freshness.py --vault "$VAULT"`：前者不帶 `--print-only` 會更新 index；後者為唯讀檢查。`export_okf.py --plan` 先列出目標，實際輸出會寫入檔案。
- `vault_backup_restore.py snapshot --vault "$VAULT" --destination "$BACKUP_DIR" --label manual --json` 建立備份；以 `verify-restore --backup <manifest> --workdir <隔離目錄> --json` 還原至暫存目錄並比對雜湊。備份和驗證會建立檔案，不應覆蓋正式 vault；必須由使用者選定目的地並授權。
- `retention_materialize.py`、`vault_materialize.py` 預設不下載；`--apply` 會要求 iCloud 下載資料，僅在明確授權時使用。

## 範圍與限制

沒有移植本機安裝包裝器、`setup.sh`、`quick-install.sh`、`build.sh`、research bootstrap、需要專案個人組態的 fixture 修補器及未經審核的批次改寫腳本。上述缺口不代表功能已驗證可用。runtime 不包含特定使用者的保留政策、檢索測試、雲端帳戶、API 金鑰或既有排程；使用者需自行建立並檢查。檢查結果不證明資料已備份、雲端同步完成或具備外部發布授權。
