# Public Bias（自作版・GitHub Actions 構成）

```
GitHub Actions（毎時05分 UTC）
  collector.py → Myfxbook (+OANDA) API → data/EURUSD.csv … をコミット
                                   │
                raw.githubusercontent.com
                                   │
MT5  PublicBiasSync（EA, 10分ごと）→ 共通フォルダ\Files\PublicBias\*.csv
MT5  PublicBias（インジケーター）  → サブウィンドウにリテール・ロング比率
```

## リポジトリ構成

```
collector.py                 収集スクリプト
config.json                  シンボル・重み設定（秘密情報は入れない）
requirements.txt
.gitignore
.github/workflows/collect.yml  毎時実行の定義
data/                        CSV が溜まる場所
mt5/PublicBiasSync.mq5       EA（ダウンロード担当）
mt5/PublicBias.mq5           インジケーター（表示担当）
```

---

## 導入手順

### STEP 1　アカウント準備
- **Myfxbook**（無料）… 未登録なら登録。メール認証まで済ませる
- **GitHub**（無料）… 未登録なら登録
- （任意）**OANDA** の API トークン … あれば 2 ソース平均になる。無くても動く

### STEP 2　GitHub にリポジトリを作る
1. 右上「＋」→ **New repository**
2. Repository name：`publicbias`、**Public** を選択 → **Create repository**
   - Private でも動くが、MT5 側にトークン設定が必要になる（後述）

### STEP 3　ファイルをアップロード
1. リポジトリ画面の「**uploading an existing file**」リンク（または Add file → Upload files）
2. zip を解凍したフォルダの中身（`collector.py` `config.json` `requirements.txt` `README.md` `.gitignore` と `data` `mt5` フォルダ）をドラッグ＆ドロップ → **Commit changes**
3. ワークフローは隠しフォルダのため、別途作成する：
   - **Add file → Create new file**
   - ファイル名欄に `.github/workflows/collect.yml` と入力（`/` を打つとフォルダになる）
   - `collect.yml` の中身を貼り付け → **Commit changes**

### STEP 4　秘密情報を登録（Secrets）
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で 3 つ登録：

| Name | Value |
|---|---|
| `MYFXBOOK_EMAIL` | Myfxbook のメールアドレス |
| `MYFXBOOK_PASSWORD` | Myfxbook のパスワード |
| `OANDA_TOKEN` | （任意）OANDA の API トークン |

※ パスワードは**絶対に config.json に書かない**こと（Public リポジトリは誰でも見える）

### STEP 5　書き込み権限を確認
**Settings → Actions → General → Workflow permissions** が「**Read and write permissions**」になっているか確認し、違えば変更して Save。

### STEP 6　手動で 1 回動かす
1. **Actions** タブ →（初回は「I understand… enable」ボタンが出たら押す）
2. 左の **collect** → **Run workflow** → **Run workflow**
3. 1 分ほどで緑のチェックになれば成功。`data/` に `EURUSD.csv` などができている
4. 赤の × なら、クリックして「Collect」のログを確認（多いのはメール/パスワード間違い）

以降は毎時自動で実行される。失敗すると GitHub から通知メールが届く。

### STEP 7　MT5 の設定
1. **ツール → オプション → エキスパートアドバイザ**
   - 「**WebRequest を許可する URL リスト**」にチェック
   - `https://raw.githubusercontent.com` を追加 → OK
2. **ファイル → データフォルダを開く**
   - `mt5/PublicBiasSync.mq5` → `MQL5\Experts\` へ
   - `mt5/PublicBias.mq5` → `MQL5\Indicators\` へ
3. MetaEditor で 2 つとも開いて **コンパイル（F7）**
4. MT5 を再起動するかナビゲーターで「更新」

### STEP 8　チャートに入れる
1. **PublicBiasSync（EA）** を**どれか 1 枚**のチャートに入れる
   - パラメータ `InpBaseUrl` の `YOUR_NAME` を自分の GitHub ユーザー名に変更
     例：`https://raw.githubusercontent.com/taro123/publicbias/main/data/`
   - チャート左上に「PublicBiasSync: 8/8 更新」と出れば OK
   - 売買は一切しない。自動売買ボタンの ON/OFF に関係なく動く
2. **PublicBias（インジケーター）** を見たいチャートに入れる
   - シンボル名は自動判定（`EURUSD#` → EURUSD、`GOLD` → XAUUSD）。合わない場合は `InpSymbol` に指定
   - サブウィンドウ名に「最新値 / 24時間変化 / 更新時刻」が表示される

---

## 運用メモ

- **収集シンボルの変更**：`config.json` の `symbols` と EA の `InpSymbols` の両方を変更
- **Myfxbook 無料枠**：100 リクエスト/24時間。毎時1回なら 24 回＋ログイン 24 回で収まる見込み
- **実行の遅れ**：GitHub Actions の定期実行は混雑時に数分〜数十分遅れたり、まれに 1 回飛ぶことがある
- **60日ルール**：Public リポジトリは 60 日間活動がないと定期実行が自動停止される。毎時のデータコミットが活動として扱われる想定だが、停止された場合は Actions タブから再有効化する
- **raw.githubusercontent.com のキャッシュ**：反映まで最大 5 分程度遅れることがある
- **Private リポジトリにしたい場合**：GitHub の Fine-grained token（対象リポジトリの Contents: Read-only）を発行し、EA の `InpToken` に入れる
- **時刻**：CSV は UTC。MT5 側で現在のサーバー時刻差を使って変換するため、夏時間切替をまたぐ過去足は 1 時間ずれる可能性あり
- **データが溜まるまで判断材料にしない**。最低数週間分は蓄積してから水準を評価する
- 本ツールは K 氏の Public Bias の考え方を公開データで近似したもの。同じ値にはならない
