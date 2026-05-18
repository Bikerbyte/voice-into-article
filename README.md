# Note Scribe

Note Scribe 是一個 Windows 桌面工具，可以錄下電腦正在播放的聲音，轉成逐字稿，並整理成 Markdown 筆記。

不需要 OpenAI API Key。轉錄使用本機的 faster-whisper，適合整理課程筆記、會議記錄、訪談內容、營運同步或工作回顧。

## 下載

[下載最新版 NoteScribe.zip](https://github.com/Bikerbyte/voice-into-article/releases/latest/download/NoteScribe.zip)

## 怎麼使用

1. 下載並解壓縮 `NoteScribe.zip`。
2. 打開資料夾裡的 `NoteScribe.exe`。
3. 選擇有 `[Loopback]` 的音效來源。
4. 選擇筆記模板，輸入標題。
5. 播放影片、音訊或會議錄影，按「開始錄音」。
6. 需要先處理一段內容時，按「轉錄目前片段」。
7. 完成後按「停止錄音」，再按「開啟資料夾」查看結果。

請保留整個解壓縮後的資料夾，不要只移動 `NoteScribe.exe`，因為程式需要旁邊的 `_internal` 檔案。

## 產出位置

用 exe 啟動時，預設會放在：

```text
文件\NoteScribe\notes\
```

常見產出檔案：

```text
xxx.md              Markdown 筆記
xxx.transcript.txt  逐字稿
xxx.prompt.md       可貼到 ChatGPT、Claude 或 Gemini 的整理提示
```

WAV 音檔預設會在轉錄成功後自動刪除，避免佔空間。只有勾選「保留 WAV」時才會留下音檔。

## 第一次使用

第一次使用某個模型時，程式會自動下載模型，所以會比較久。下載完成後，下次就會快很多。

建議先用 `base` 模型；如果電腦比較慢，可以改用 `tiny`。

## 常見問題

**沒有錄到聲音**

請確認音效來源選的是有 `[Loopback]` 的裝置，而且音訊正在播放。

**轉錄很慢**

可以改用 `tiny` 模型，速度會比較快，但準確度可能會下降。

**筆記想整理得更完整**

可以把 `*.prompt.md` 的內容貼到 ChatGPT、Claude 或 Gemini，請它整理成文章、會議記錄或工作摘要。

## 開發

這個專案的目標是做成通用的本機聲音轉筆記工具。主要技術包含 Python、Tkinter、WASAPI loopback、faster-whisper 與 PyInstaller。
