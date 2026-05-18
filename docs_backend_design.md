# バーコード資産管理アプリ バックエンド設計（初版）

このドキュメントは `README.md` の要件を実装するための、API・DB・処理フローの初期設計です。

## 1. 想定アーキテクチャ
- クライアント: Web（バーコードリーダー入力/カメラ入力）
- API: REST
- DB: RDBMS（PostgreSQL想定）
- ファイル取込: CSV/XLSXをサーバーでパースしてバリデーション

---

## 2. DBスキーマ（DDL案）

```sql
CREATE TABLE assets (
  asset_id            UUID PRIMARY KEY,
  barcode             VARCHAR(128) NOT NULL UNIQUE,
  asset_name          VARCHAR(255) NOT NULL,
  category            VARCHAR(100),
  location            VARCHAR(255),
  registered_at       DATE NOT NULL,
  last_confirmed_at   TIMESTAMP NULL,
  status              VARCHAR(50) NOT NULL DEFAULT 'active',
  is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at          TIMESTAMP NULL,
  deleted_by          VARCHAR(100) NULL,
  delete_comment      TEXT NULL,
  created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_assets_name ON assets(asset_name);
CREATE INDEX idx_assets_registered_at ON assets(registered_at);
CREATE INDEX idx_assets_last_confirmed_at ON assets(last_confirmed_at);
CREATE INDEX idx_assets_active ON assets(is_deleted, status);

CREATE TABLE scan_logs (
  scan_log_id         BIGSERIAL PRIMARY KEY,
  scanned_code        VARCHAR(128) NOT NULL,
  result              VARCHAR(20) NOT NULL, -- success / not_found / error
  asset_id            UUID NULL,
  message             VARCHAR(500),
  scanned_at          TIMESTAMP NOT NULL DEFAULT NOW(),
  scanned_by          VARCHAR(100) NULL
);

CREATE INDEX idx_scan_logs_scanned_at ON scan_logs(scanned_at);
CREATE INDEX idx_scan_logs_code ON scan_logs(scanned_code);

CREATE TABLE audit_logs (
  audit_log_id        BIGSERIAL PRIMARY KEY,
  action              VARCHAR(20) NOT NULL, -- create / update / delete / import
  target_asset_id     UUID NULL,
  before_json         JSONB NULL,
  after_json          JSONB NULL,
  acted_at            TIMESTAMP NOT NULL DEFAULT NOW(),
  acted_by            VARCHAR(100) NULL,
  comment             VARCHAR(500) NULL
);

CREATE INDEX idx_audit_logs_acted_at ON audit_logs(acted_at);
CREATE INDEX idx_audit_logs_target ON audit_logs(target_asset_id);
```

---

## 3. API設計（v1）

## 3.1 バーコード読取
### `POST /api/v1/scan`

**Request**
```json
{
  "barcode": "ABC-000123",
  "scanned_by": "user01"
}
```

**Success (200)**
```json
{
  "result": "success",
  "asset": {
    "asset_id": "...",
    "barcode": "ABC-000123",
    "asset_name": "ノートPC",
    "location": "3F-営業部",
    "last_confirmed_at": "2026-05-18T09:00:00Z"
  }
}
```

**Not Found (404)**
```json
{
  "result": "not_found",
  "message": "asset not found for barcode"
}
```

**処理要点**
1. `barcode` を正規化（前後空白除去）
2. `assets` から `is_deleted = false` で検索
3. 見つかれば `last_confirmed_at = NOW()` 更新
4. `scan_logs` 記録
5. 結果返却

---

## 3.2 資産検索
### `GET /api/v1/assets`

**Query Parameters**
- `asset_name` (partial)
- `barcode` (exact)
- `registered_from`, `registered_to`
- `confirmed_from`, `confirmed_to`
- `location`, `category`
- `unconfirmed_only` (`true/false`)
- `inventory_from`, `inventory_to` （棚卸し期間）
- `page`, `page_size`

**棚卸し未確認ロジック（例）**
- `unconfirmed_only=true` の時、下記条件を適用
  - `last_confirmed_at IS NULL`
  - または `last_confirmed_at < inventory_from`

---

## 3.3 資産登録
### `POST /api/v1/assets`
- `barcode` 重複時は `409 Conflict`
- 成功時に `audit_logs(action=create)` を記録

## 3.4 資産更新
### `PUT /api/v1/assets/{asset_id}`
- 更新前後の差分を `audit_logs` に保存

## 3.5 資産削除（論理削除）
### `DELETE /api/v1/assets/{asset_id}`

**Request**
```json
{
  "deleted_by": "user01",
  "delete_comment": "廃棄済みのため"
}
```

**ルール**
- `delete_comment` 必須
- `is_deleted=true`, `deleted_at`, `deleted_by`, `delete_comment` を更新
- `audit_logs(action=delete)` 記録

---

## 3.6 インポート
### `POST /api/v1/assets/import`
- 対応: `csv`, `xlsx`
- バリデーション:
  - 必須欠損（barcode, asset_name, registered_at）
  - barcode重複（ファイル内・DB内）
  - 日付フォーマット
- 検証結果を行番号付きで返却

---

## 4. エラーコード方針
- `400` リクエスト不正
- `404` 該当データなし
- `409` 重複（barcode）
- `422` バリデーションエラー
- `500` サーバー内部エラー

---

## 5. 実装優先順（推奨）
1. DBマイグレーション（assets/scan_logs/audit_logs）
2. `POST /scan` と連続読取UIの疎通
3. `GET /assets`（未確認抽出を含む）
4. CRUD + 論理削除 + 監査ログ
5. import機能（csv/xlsx）
6. CSVエクスポート

