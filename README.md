# route

`route` 是一個專為 Claude Code 設計的模型路由 (Model-Routing) 插件。其核心目標是**將昂貴的高階模型從機械式的執行工作中解放出來**：主會話（Boss）專注於高階規劃與決策，四個專屬子代理人（Subagents）則分工處理地圖繪製、代碼實作、風險審查與日誌謄寫。

| 角色 (Role) | 執行位置 | 預設模型與 Effort | 負責範疇 (Owns) | 絕對禁止 (Must Never) |
|---|---|---|---|---|
| **Boss** | 主會話 (Main Thread) | 您的 Session 模型 | 路由分級、順序排定、規格/簡報撰寫、結果裁決 | 撰寫生產程式碼、直接編輯追蹤記錄 |
| **scout** | 子代理人 (Subagent) | `haiku` (low effort, 30 turns) | 探索代碼拓撲、壓縮長日誌與堆疊追蹤 | 撰寫任何檔案、執行任何 Bash 指令 |
| **builder** | 子代理人 (Subagent) | `sonnet` (high effort, 60 turns) | 依據 Spec/Brief 實作代碼、執行驗證 | 變更測試檔案、修改 Spec、修改追蹤文檔 |
| **reviewer** | 子代理人 (Subagent) | `sonnet` (high effort, 40 turns) | 比對 Diff 與 Spec，檢查 7 大風險觸發器 | 修復問題、提出修復建議、執行任何指令 |
| **scribe** | 子代理人 (Subagent) | `haiku` (low effort) | 將任務成果謄寫至 `docs/agent/` 追蹤記錄 | 撰寫生產程式碼 |

角色權限邊界透過 `PreToolUse` Hooks 進行強制攔截與分類防護。Hook 採用安全防護優先原則，並在輸入格式異常時預設放行 (Fail-open) 以避免阻斷主會話。

---

## 系統需求

- Python 3.8 或更高版本，且 `python3` 必須在 `PATH` 中。
- **零外部套件依賴** — 插件的 Hooks 僅使用 Python 標準函式庫。

---

## 安裝方式

### 在 Claude Code 會話內

```
/plugin marketplace add CTJ425/Model-Routing
/plugin install route@route
```

### 在終端機 (CLI)

```bash
claude plugin marketplace add CTJ425/Model-Routing
claude plugin install route@route
```

安裝完成後，在任何目標專案目錄下執行：

```
/route:init      # 透過互動問答建立 .claude/route.config.json 配置檔
/route:config    # 檢視或動態調整各角色開關、模型等級、審查政策與防護門檻
```

---

## 更新方式

插件安裝於 **user scope**（`~/.claude/plugins/`），因此更新一次，您所有的專案都會同步套用新版本。

更新需要兩個步驟：先刷新 marketplace 的本地 clone，才能取得新版本；再更新插件本身。

### 在終端機 (CLI)

```bash
claude plugin marketplace update route     # 步驟 1：刷新 marketplace clone
claude plugin update route@route           # 步驟 2：更新插件
claude plugin list                         # 驗證：確認 Version 與 Scope
```

### 在 Claude Code 會話內

```
/plugin marketplace update route    # 步驟 1：刷新 marketplace clone
/plugin                             # 步驟 2：於互動面板中更新 route
```

> **注意**：會話內**沒有** `/plugin update <plugin>` 這個子指令。`update` 只存在於 marketplace 層級 (`/plugin marketplace update`) 與 CLI (`claude plugin update`)。插件本身的更新請使用互動式 `/plugin` 面板。

### 更新後必須重啟

CLI 會回覆 `Restart to apply changes`。**重啟前，當前會話仍在執行舊版的 Hooks。** 若不確定實際生效的版本，執行 `/route:doctor` 或 `claude plugin list` 進行確認。

### 請勿手動 pull marketplace clone

`~/.claude/plugins/marketplaces/route` 由 Claude Code 與其版本快取 (`~/.claude/plugins/cache/`) 一併管理。手動 `git pull` 會使兩者失同步——clone 指向新版 commit，但快取仍是舊版目錄，且插件實際載入的是快取。請一律使用上述指令。

### 專案設定不受更新影響

`.claude/route.config.json` 屬於**專案設定**，不是安裝內容。插件更新既不會覆蓋它，也不會將它帶入其他專案。這也是各角色的模型等級應透過 `/route:config` 調整、而非手改 Agent frontmatter 的原因——frontmatter 位於 user scope 的快取目錄中，下次更新即會被覆寫。

---

## 系統架構與路由生命週期

![route Architecture](docs/architecture.svg)

### 7 階段路由生命週期 (Step 0 ~ Step 6)

模型路由迴圈涵蓋 7 個精確階段，具備自動角色邊界防護與重試裁決迴圈：

```
[0. 任務分級 Lane] ──► [1. Scout (地圖探索)] ──► [2. Boss (規格擬定)] ──► [3. Builder (代碼實作)]
                                                                                │
[6. Scribe (成果記帳)] ◄── [5. Boss (結果裁決)] ◄── [4. Reviewer (風險審查)] ◄┘
         ▲                          │
         └──────── (Lane 0) ────────┴──► [裁決迴圈：定位修復 / 修正規格 / 升級人工]
```

1. **Step 0 — 任務分級與分派門檻評估 (`Boss`)**：
   - 評估任務風險與推論需求，並計算任務規模是否超過子代理人的冷啟動開銷（Cold-start Overhead）。
   - **Lane 0 (極小就地修改)**：低於分派門檻的單行修復或版本號更新。Boss 直接在主會話中修改、驗證並完成單行記錄。
   - **Lane 1 (邊界明確的功能/修復)**：已知模組內的常規修改。Boss 撰寫行內簡報（5 段式 Inline Brief）。
   - **Lane 2 (高風險/跨模組變更)**：複雜缺陷、狀態/資料庫變更、認證或 API 邊界。Boss 撰寫完整規格檔案（Spec）並先編寫失敗測試。

2. **Step 1 — 程式碼拓撲繪製 (`scout` | Haiku 預設，Low Effort)**：
   - 僅在目標區域尚未探索時分派。執行唯讀掃描，回傳約 40 行的結構化地圖摘要。
   - **預算規範**：預設上限 `maxTurns: 30`（不支援專案自訂覆寫）。每次分派請給予**單一明確問題**並在已知時提供行號範圍；若在單次提示中堆疊多個跨大檔案的問題，將耗盡 30 回合預算而無法回傳可用資訊。若預算不足，Scout 會遵循優雅降級協議，以 `NOT ANSWERED:` 明列未完部分，呼叫端可透過 `SendMessage` 恢復會話續問。

3. **Step 2 — 規格與簡報撰寫 (`Boss` | Session 模型)**：
   - 高階模型撰寫任務契約、完整 `Files` 異動檔案清單、精確的 `Verify` 驗證指令與 `Non-goals`（非目標）。Boss 絕對不直接編寫生產代碼。

4. **Step 3 — 程式碼實作 (`builder` | Sonnet 預設，High Effort)**：
   - 讀取 Spec/Brief，嚴格在指定的 `Files` 清單內實作變更，並照字面（Verbatim）原樣執行驗證指令與測試套件。

5. **Step 4 — 審查與風險檢查 (`reviewer` | Sonnet 預設，High Effort)**：
   - 依據 `review.policy`（`always`、`risk` 或 `never`）觸發。Boss 以外部 Diff 形式提供變更內容，讓審查者直接閱讀 Diff 差異而非重新讀取全量檔案。
   - 評估 7 大風險觸發器（`no_red_green`、`persistent_state`、`authorization`、`boundary`、`silent_calculation`、`control_flow`、`builder_blocker`）以及 5 項常態檢查（Standing Checks）。只回報問題清單（`BLOCKER` / `RISK`），不提出具體修復方案。

6. **Step 5 — 裁決與反饋迴圈 (`Boss` | Session 模型)**：
   - **PASS**：直接推進至 Step 6。
   - **FAIL (第 1 次)**：Boss 撰寫精確定位修復指令（檔案 + 行號 + 後置條件），並透過 `SendMessage` 恢復先前已分派的 `builder` 繼續修復（保留先前的上下文，避免重複支付冷啟動開銷）。
   - **FAIL (第 2 次)**：約 80% 機率為規格本身存在瑕疵。Boss 修正 Spec/Brief 後重啟實作。
   - **FAIL (第 3 次)**：終止自動化迴圈，升級交由人工工程師介入。

7. **Step 6 — 成果記帳與審計存檔 (`scribe` | Haiku 預設，Low Effort)**：
   - 將已驗證的成果、測試統計、Lint 結果、審查結論與殘留風險以機械化方式追加至 `docs/agent/PROGRESS.md`、`TASK.md` 與 `BUG_FIX.md`，並依設定自動歸檔。

> 💡 載入 `route` Skill（或直接開啟新功能/修復任務 — `SessionStart` Hook 會主動提示委派流程），系統將逐步引導您走過此迴圈。

---

## 專案獨立配置 (.claude/route.config.json)

每個專案均可在根目錄下建立專屬的 `.claude/route.config.json`。所有設定鍵值皆為選填，Hooks 會將專案設定與內建預設值進行深度合併（Deep-merge），完整 Schema 規格定義於 `route/schema/route.config.schema.json`。

```json
{
  "version": 2,
  "paths": {
    "prod": ["src/"],
    "test": ["tests/", "**/*.test.ts"],
    "docs": "docs/agent",
    "specs": "docs/agent/specs"
  },
  "models": {
    "scout": "haiku",
    "builder": "sonnet",
    "reviewer": "sonnet",
    "scribe": "haiku"
  },
  "roles": {
    "scout": { "enabled": true },
    "builder": { "enabled": true },
    "reviewer": { "enabled": true },
    "scribe": { "enabled": true }
  },
  "bookkeeping": {
    "enabled": true,
    "timezone": "Asia/Taipei"
  },
  "review": {
    "policy": "risk"
  },
  "guard": {
    "mainSeverity": "ask",
    "readKB": 64,
    "scoutAt": 2,
    "bashWriteDetection": true
  }
}
```

### 設定鍵值說明

- `paths.prod`：生產代碼的相對路徑或 Glob 規則，Guard 會據此界定生產代碼範圍。
- `paths.test`：測試檔案路徑規則，Guard 會嚴禁 `builder` 擅自修改此範圍。
- `models.<role>`：針對此專案覆寫該角色的分派模型（支援任何別名或完整模型 ID）。此設定僅作用於分派參數，不會修改插件本體檔案；若環境變數 `CLAUDE_CODE_SUBAGENT_MODEL` 已設定，該環境變數優先度高於此處設定。
- `roles.<role>.enabled`：設為 `false` 可完全關閉特定角色（四個角色均可獨立關閉）。關閉後 Guard 會直接拒絕（Deny）該角色的分派，Session 簡報會將其從名單中移除，並由主會話接管該步驟工作。
- `bookkeeping.enabled`：設為 `false` 時僅啟用模型路由功能（不分派 `scribe`、不維護追蹤文檔、Guard 不套用記錄保護規則）。
- `bookkeeping.timezone`：寫入記錄時間戳時所採用的 IANA 時區（如 `UTC` 或 `Asia/Taipei`）。
- `review.policy`：審查觸發策略：`always`（每次實作後均審查）、`risk`（預設，僅在觸發風險時審查）、`never`（不審查，以測試作為唯一門檻）。
- `review.triggers`：自訂風險觸發器清單（`no_red_green`、`persistent_state`、`authorization`、`boundary`、`silent_calculation`、`control_flow`、`builder_blocker`）。
- `guard.mainSeverity`：當主會話嘗試直接修改生產代碼或追蹤文檔時的防護層級（`ask`、`deny`、`off`）。
- `guard.readKB`：主會話未指定範圍讀取大檔案的警示上限（KB），超過時要求確認；`0` 為關閉。
- `guard.scoutAt`：主會話在手動搜尋檔案達到指定次數時，主動提示改用 `scout`；`0` 為關閉。
- `guard.bashWriteDetection`：是否啟用 Bash 檔案寫入啟發式偵測（預設 `true`）。

> 執行 `/route:init` 可建立初始配置檔；執行 `/route:config` 可檢視與互動式編輯。

---

## 驗證與審計工具

```
/route:doctor    # 診斷插件健康狀態：直譯器、Hooks 執行性與配置檔檢查
/route:audit     # 統計主會話與各 Subagents 的 Token 消耗與花費 (USD)
/route:delta     # 評估各次分派是否成功減少主會話的 Context 淨負擔
```

- **/route:doctor**：當路由行為異常時的第一道檢查工具。它能驗證 Hooks 是否正常被呼叫並檢查 Python 直譯器狀態（僅做狀態診斷，不自動修改檔案）。
- **/route:audit** 與 **/route:delta**：直接解析 Claude Code 原生生成的 Transcripts。若發現僅有主模型消耗且無任何 Subagent 紀錄，代表分派未實際生效。USD 費用依據 `route/scripts/pricing.json` 計算（可透過專案設定自訂費率表）。

---

## 安全邊界與防護限制說明 (What this does NOT enforce)

- **透過 Bash 執行的檔案寫入**：Guard 對 Shell 指令的偵測基於正規表示式啟發（Regex Heuristics），無法涵蓋 100% 的複雜語法。真正的核心防護在於 `tools` 白名單：`scout` 與 `reviewer` 完全未賦予 Bash 工具。針對有寫入範圍的角色，0.9.0 之後 Guard 會解析指令的實際寫入目標，並套用與 `Write`／`Edit` 完全相同的範圍：`builder` 可在 `paths.prod` 內執行 `mkdir`／`mv`／`rm` 等檔案工具無法表達的操作，超出範圍則直接拒絕（`deny`）。無法解析出字面路徑的寫入指令，對有寫入範圍的角色一律拒絕。Scribe 在 `paths.docs` 內的精確 `cat >> <path>` 追加寫入依然被安全允許。
- **主會話透過 Bash 的寫入**：0.9.0 之後同樣受 `guard.mainSeverity` 管制。在此之前 `sed -i`、heredoc 等 Shell 寫入完全繞過主會話防護——在「優先使用 Bash 編輯檔案」的自動模式下，這等同於靜默關閉 Step 3／Step 6 的分派提示。若指令無法解析出字面路徑，對主會話一律放行（Fail-open：絕不因解析失敗而阻斷主會話）。
- **專案目錄之外的路徑**：解析結果位於專案根目錄外的路徑不受 Guard 判定與管制。
- **非插件所屬的自定義 Agent**：未知的 `agent_type` 不會受到此處規則限制；本 Guard 專責管理路由插件所定義的角色。
- **模型實際計費扣款**：Hooks 僅記錄分派與呼叫；實際費用請使用 `/route:audit` 進行對帳。
- **Builder 的任務層級 `Files` 清單**：Guard 負責角色層級的路徑類別防護；Task 具體的檔案清單需由 Builder 嚴格自我約束與 Reviewer 進行審查。

### Fail-open 設計與 Python 環境依賴

所有的 Guard 在設計上皆為 **Fail-open**（當負載格式異常、設定檔損毀或 Hook 發生例外時，皆會安靜放行，絕不阻斷您的開發會話）。

這代表一個關鍵前提：Hooks 依賴 `python3` 指令執行。若 Claude Code 傳遞給 Hook 的 `PATH` 中無法解析 `python3`（例如某些 Windows 環境或未加入 PATH 的虛擬環境），所有 Hooks 將會靜默放行而失去防護功能。

> ⚠️ **會話啟動時的 `[routing]` 簡報是核心指標（Canary）**：若在 Session 開頭未看見 `[routing]` 簡報，代表 Hooks 尚未運行。可立即執行 `/route:doctor` 進行診斷修復。

---

## 語言政策 (Language)

- 程式碼、識別碼與 Git Commit 訊息維持使用**英文**。
- 追蹤文檔與 Agent 產生的報告語言遵循配置檔中的 `language.artifacts`（例如 `zh-TW` 或 `en`）。
- 本 `README.md` 採用繁體中文作為使用者主要參考文件。

---

## 授權條款 (License)

本專案基於 [MIT License](LICENSE) 授權開源。
