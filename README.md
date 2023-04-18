# ChatGPT_Maya
MayaからChatGPT API（[gpt-3.5-turbo](https://platform.openai.com/docs/guides/chat)）を呼び出し、Python/MELスクリプトを生成・実行するGUIです。  

> テスト環境 :
> * Windows 10/11
> * Maya 2023 (Python3.9.7)
> * Maya 2024 (Python3.10.8)

## インストール
1. [Account API Keys - OpenAI API](https://platform.openai.com/account/api-keys)よりAPI Keyを取得し、環境変数`OPENAI_API_KEY`に設定する  

2. Mayaを起動していない状態で`install\install_maya20XX_win.bat`を実行する。

## 使用方法
```python
import chatmaya
chatmaya.run()
```

* 左側下部のテキストフィールドにプロンプトを打ち込み送信ボタンを押すとAPIにリクエストが送信され返答が表示されます。
* 返答はPython/MELコードとその他の部分に分解されそれぞれのフィールドに表示されます。
* 返答に複数のコードブロックが書いてあった場合は、右側下部のプルダウンから選択出来るようになります。
* New Chatを押すかウィンドウを閉じるまでは、会話履歴が残ります。
* ログや設定ファイルは`C:\Users\<ユーザー名>\Documents\maya\ChatMaya`に出力されています。
* 別途[VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine)が起動していると、自動的にコードブロック以外の部分の読み上げが行われます。使用する場合はGPUモード推奨です。

![example3](.images/example3.png)

## アンインストール
以下のフォルダを削除すればアンインストールされます。
* `C:\Users\<ユーザー名>\Documents\maya\<Mayaバージョン>\scripts\chatmaya`
* `C:\Users\<ユーザー名>\Documents\maya\ChatMaya`

追加パッケージは`pip uninstall`で個別に行うか以下のフォルダを丸ごと削除してください。
* `C:\Users\<ユーザー名>\Documents\maya\<Mayaバージョン>\site-packages`

## リンク
### 解説, サンプル
※[beta](https://github.com/akasaki1211/ChatGPT_Maya/tree/beta)時点での解説です
* [ChatGPT API を使用してMayaを（Pythonスクリプトで）操作してもらう - Qiita](https://qiita.com/akasaki1211/items/34d0f89e0ae2c6efaf48)
* [サンプル(Twitter)](https://twitter.com/akasaki1211/status/1632704327340150787)

### コード参考
* [ChatGPT APIを使ってAIキャラクターを作ってみる！ - Qiita](https://qiita.com/sakasegawa/items/db2cff79bd14faf2c8e0)
* [【Python】ChatGPT APIでウェブサイト版のように返答を逐次受け取る方法 - Qiita](https://qiita.com/Cartelet/items/cfc07fc499b6ebbc7dde)