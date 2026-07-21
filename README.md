# 羽田空港P3駐車場 空き通知(GitHub Actions + ntfy.sh)

7/26・7/27のP3(第2ターミナル)駐車場に空きが出たら、ntfy.sh経由でスマホに通知します。

## セットアップ手順

### 1. ntfyアプリをインストールして購読する
1. スマホに ntfy アプリをインストール(iOS App Store / Google Play)
2. アプリ内で「+」から新しいトピックを購読する
   - トピック名は自由な文字列(例: `haneda-p3-<ランダムな文字列>`)
   - **注意**: ntfy.shのトピックは名前さえ知っていれば誰でも購読・投稿できる
     公開の仕組みです。他人に推測されないよう、ランダムな文字列を
     含めた名前にしてください(例: `haneda-p3-x7k2m9`)

### 2. このリポジトリをGitHubにpushする
```
git init
git add .
git commit -m "haneda parking notify"
git remote add origin <あなたのリポジトリURL>
git push -u origin main
```

### 3. GitHub Secretsを設定
リポジトリの Settings → Secrets and variables → Actions で以下を追加:
- `NTFY_TOPIC` … 手順1で決めたトピック名

### 4. `check_availability.py` の `find_day_status()` を実装する
このファイルはまだ未完成です。ブラウザの開発者ツールでP3一般車枠カレンダーの
日付セルのHTML(空車/混雑/満車の表現方法)を確認し、TODOコメントの箇所を
実装してください。分からない場合は該当セルのHTMLをClaudeに貼れば、
そこを完成させられます。

### 5. 動作確認
- ローカルで試す場合: `NTFY_TOPIC=your-topic python check_availability.py`
- GitHub Actionsの「Actions」タブから `workflow_dispatch` で手動実行し、
  ログを確認する

## 注意事項
- cronは15分おきに設定していますが、頻度が高すぎるとサイトに負荷をかけたり
  利用規約(アクセス監視について言及あり)に抵触する可能性があります。
  頻度は必要最小限(例: 30分〜1時間おき)に調整することをおすすめします。
- このサイトの利用規約・アクセス監視に関する記載を必ず確認し、
  自動アクセスが許容される範囲かご自身でご確認ください。
- ntfy.shは無料の公開サービスです。機微な情報を含めたくない場合や
  より確実性を求める場合は、自前でntfyサーバーを立てることも可能です
  (今回の用途では公開サービスで十分と思われます)。
