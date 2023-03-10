# ChatGPT_Maya
MayaからChatGPT API（[gpt-3.5-turbo](https://platform.openai.com/docs/guides/chat)）を呼び出し、Pythonスクリプトを生成・実行させるGUIです。  

テスト環境 :
* Maya 2023 (Python3.9.7)
* openai 0.27.0

## 環境構築
> **Note**  
> 以下はAnaconda仮想環境を使用していますが、`openai`がMayaから呼び出せればどんな方法でも問題ありません。

1. [Account API Keys - OpenAI API](https://platform.openai.com/account/api-keys)よりAPI Keyを取得し、環境変数`OPENAI_API_KEY`に設定する  


2. 仮想環境を作成しMayaと同じバージョンのPythonを入れる
```
conda create -n maya2023 python=3.9.7
conda activate maya2023
```

3. 仮想環境に`openai`を入れる
```
pip install openai
```

4. `PYTHONPATH`に仮想環境のパッケージフォルダ`~\site-packages`を追加し、Maya起動する
```batchfile
@echo off
set PYTHONPATH=%UserProfile%\Anaconda3\envs\maya2023\Lib\site-packages
start "" "%ProgramFiles%\Autodesk\Maya2023\bin\maya.exe"
exit
```

## 使用方法
Mayaから[chatgpt_maya.py](chatgpt_maya.py)を実行するとUIが表示されます。

* 上部のテキストフィールドに命令を打ち込み、テンキーのEnterを押すか、送信ボタンを押すとAPIに送信され返答が下部に表示されます。
* 返答はPythonコードとその他の部分に分解されそれぞれのフィールドに表示されます。分解前の返答はScriptEditorに出力されています。
* ChatGPTが複数のコードブロックを書いてきた場合は、Scriptsプルダウンから選択出来るようになります。
* リセットボタンを押すかウィンドウを閉じるまでは、直前までの会話を記憶した状態になります。
* ログボタンを押すとScriptEditorに会話ログが出力されます。

![example1](.images/example1.png)
![example2](.images/example2.png)

## リンク
### 解説, サンプル
* [ChatGPT API を使用してMayaを（Pythonスクリプトで）操作してもらう - Qiita](https://qiita.com/akasaki1211/items/34d0f89e0ae2c6efaf48)
* [サンプル(Twitter)](https://twitter.com/akasaki1211/status/1632704327340150787)

### コード参考
* [ChatGPT APIを使ってAIキャラクターを作ってみる！ - Qiita](https://qiita.com/sakasegawa/items/db2cff79bd14faf2c8e0)
* [【Python】ChatGPT APIでウェブサイト版のように返答を逐次受け取る方法 - Qiita](https://qiita.com/Cartelet/items/cfc07fc499b6ebbc7dde)