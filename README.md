 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/README.md b/README.md
new file mode 100644
index 0000000000000000000000000000000000000000..79badbd4f8c6603dd45e9a05fb0e4cbb96f7901f
--- /dev/null
+++ b/README.md
@@ -0,0 +1,114 @@
+# 資産バーコード管理アプリ 要件定義
+
+本リポジトリは、バーコードを用いた資産棚卸し・検索・登録編集を行うアプリの仕様を定義します。
+
+## 目的
+- 資産にバーコードを貼付し、読み取りで資産特定と確認記録を効率化する。
+- Excel/CSVで管理されている資産リストを取り込み、検索・更新・棚卸しに活用する。
+
+## 想定データソース
+- 取込フォーマット: Excel (`.xlsx`) / CSV (`.csv`)
+- 主キー: `barcode`（重複不可）
+
+---
+
+## 1. 読み取り機能
+
+### 要件
+- バーコード読取時、登録済み資産から一致検索し、資産詳細をポップアップ表示する。
+- 一致資産の `last_confirmed_at`（確認日）を更新する。
+- 連続読取を可能とし、1件処理後は自動で次の読取待受に戻る。
+- 未登録バーコードはエラー表示し、エラーログへ記録する。
+
+### UX要件
+- 連続読取中でも画面遷移しない。
+- 同一コードの短時間重複読み取りを抑止（例: 1〜2秒デバウンス）。
+- 成功・失敗をトースト表示し、直近履歴を画面に残す。
+
+---
+
+## 2. 検索機能
+
+### 検索条件
+- 確認日（From / To）
+- 登録日（From / To）
+- 資産名称（部分一致）
+- バーコード（完全一致）
+- 設置場所 / カテゴリ（任意）
+
+### 棚卸し支援
+- 「未確認資産のみ」抽出:
+  - `last_confirmed_at IS NULL`
+  - または指定棚卸し期間に未確認
+- 検索結果のCSVエクスポート
+
+---
+
+## 3. 登録・編集・削除機能
+
+### 登録
+- 新規資産を登録可能。
+- 必須項目: `barcode`, `asset_name`, `registered_at`。
+
+### 編集
+- 資産名称、カテゴリ、設置場所、状態等を更新可能。
+- 更新者・更新日時を保存。
+
+### 削除
+- 論理削除を採用（`is_deleted = true`）。
+- 削除時にコメント入力を必須化。
+- 削除操作を監査ログに記録（実行者、日時、コメント）。
+
+---
+
+## データモデル（最小）
+
+| カラム | 型 | 説明 |
+|---|---|---|
+| asset_id | UUID / BIGINT | 内部ID |
+| barcode | string | バーコード（ユニーク） |
+| asset_name | string | 資産名称 |
+| category | string | 分類 |
+| location | string | 設置場所 |
+| registered_at | date/datetime | 登録日 |
+| last_confirmed_at | datetime nullable | 最終確認日 |
+| status | string | 利用状態（active/disposed など） |
+| is_deleted | boolean | 論理削除フラグ |
+| deleted_at | datetime nullable | 削除日時 |
+| deleted_by | string nullable | 削除者 |
+| delete_comment | text nullable | 削除コメント |
+| created_at | datetime | 作成日時 |
+| updated_at | datetime | 更新日時 |
+
+---
+
+## ログ要件
+
+### 読取ログ
+- `scan_logs` に成功/失敗を記録
+- 項目例: `scanned_code`, `result`, `asset_id`, `message`, `scanned_at`, `scanned_by`
+
+### 監査ログ
+- 登録・編集・削除の変更履歴を記録
+- 項目例: `action`, `target_asset_id`, `before_json`, `after_json`, `acted_at`, `acted_by`
+
+---
+
+## 受け入れ基準（抜粋）
+
+1. 登録済みバーコードを読み取ると、1秒以内に資産情報が表示され、確認日が当日更新される。
+2. 未登録バーコードは資産更新されず、エラーが表示される。
+3. 検索画面で「未確認資産のみ」を指定すると、確認日未入力または期間外の資産だけが表示される。
+4. 削除時にコメント未入力では削除できない。
+5. 削除実行時、監査ログに記録が残る。
+
+---
+
+## 次フェーズ（実装タスク）
+1. CSV/Excel取込バリデータ実装（重複・必須欠損チェック）
+2. 資産マスタCRUD API実装
+3. バーコード読取API（確認日更新含む）
+4. 検索API（未確認抽出対応）
+5. 監査ログ/読取ログ実装
+6. フロント画面（読取・検索・編集）実装
+
 
EOF
)
