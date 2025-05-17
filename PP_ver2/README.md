# PP - AIパーソナル学習アシスタント

## 概要
PPは、AIを活用して動的に問題を生成する学習支援アプリケーションです。Google Gemini AIを利用して、ランダムな問題を生成することで、記憶による学習を防ぎ、真の理解を促進します。

## 主な機能

### 1. クイズ機能
- **4択クイズ**
  - AIによる動的な問題生成
  - 即時の正誤判定
  - 結果のフィードバック表示

- **記述式クイズ**（実装予定）
  - 自由記述形式の回答
  - AIによる回答評価
  - 詳細なフィードバック提供

### 2. 学習管理機能
- 学習履歴の記録
- 進捗状況の可視化
- 正答率の追跡

### 3. 対応科目
- 現在：日本の歴史
- 今後の拡張予定：
  - 国語
  - 数学
  - 英語
  - 理科

## 技術スタック

### フレームワークとライブラリ
- **Streamlit** (v1.32.0)
  - Webアプリケーションフレームワーク
  - インタラクティブなUI/UX
  - クラウドデプロイメント

- **Google Generative AI** (v0.3.2)
  - Gemini 2.0 Flash モデル使用
  - 動的な問題生成
  - 回答評価

- **SQLite**
  - 学習履歴の保存
  - ユーザーデータの管理
  - ローカルデータベース

- **Python-dotenv** (v1.0.0)
  - 環境変数管理
  - APIキーの安全な取り扱い

### データベース設計
```sql
CREATE TABLE learning_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    question TEXT,
    user_answer TEXT,
    correct_answer TEXT,
    is_correct BOOLEAN
)
```

## セットアップ方法

### ローカル環境での実行
1. リポジトリのクローン
```bash
git clone [リポジトリURL]
cd PP_ver2
```

2. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

3. アプリケーションの起動
```bash
streamlit run pp.py
```

### Streamlit Cloudでの実行
1. GitHubにコードをプッシュ
2. Streamlit Cloudでデプロイ
3. 環境変数の設定
   - Streamlit Cloud設定でSecretsを追加
   ```toml
   GOOGLE_API_KEY = "your_api_key_here"
   ```

## 使用方法
1. アプリケーションにアクセス
2. サイドバーから学習モードを選択
   - 4択クイズ
   - 記述式クイズ（予定）
   - 学習ログ
3. 「新しい問題を生成」ボタンをクリック
4. 問題に回答
5. 結果とフィードバックを確認

## 注意事項
- Google API Keyの適切な管理が必要
- APIの使用制限に注意
- 定期的なAPIキーのローテーションを推奨

## 今後の展開
1. 記述式問題の実装
2. 追加科目のサポート
3. 詳細な学習分析機能
4. カスタマイズ可能な難易度設定
5. ユーザー認証システムの導入

## ライセンス
このプロジェクトはMITライセンスの下で公開されています。

## 作者
[作者名]

## 貢献
バグ報告や機能改善の提案は、GitHubのIssueやPull Requestsで受け付けています。 