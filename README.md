# Exam Scribe

Exam Scribe 是一個 Windows 桌面工具，可以錄下電腦正在播放的課程聲音，轉成逐字稿，並產生備考用的 Markdown 筆記草稿。

它不需要 OpenAI API key。轉錄使用本機的 `faster-whisper`，適合拿來一邊看課程、一邊整理考試筆記。

## 適合誰用

- 想把線上課程整理成備考筆記的人
- 想記 AWS SAA-C03、CCNA 或其他考試重點的人
- 不想手動開指令、不想自己剪音檔的人

## 下載與啟動

1. 下載 `ExamScribe.zip`。
2. 解壓縮整個 zip。
3. 打開資料夾裡的 `ExamScribe.exe`。
4. 播放課程影片，按「開始錄音」。

不要只單獨移動 `ExamScribe.exe`，請保留整個解壓縮後的資料夾，因為程式需要旁邊的 `_internal` 檔案。

## 基本使用方式

1. 選擇音效來源：通常選有 `[Loopback]` 的喇叭或耳機。
2. 選擇考試 Profile：預設是 `aws-saa-c03`。
3. 輸入筆記標題。
4. 按「開始錄音」。
5. 看到一個段落結束時，按「轉錄目前片段」。
6. 全部看完後，按「停止錄音」。
7. 按「開啟資料夾」查看產出的筆記。

如果不想一直手動按，也可以勾選「自動每 N 秒轉錄」，例如填 `30`，程式就會大約每 30 秒自動切出一段來處理。

## 產出的檔案在哪裡

用 exe 啟動時，預設會放在：

```text
文件\ExamScribe\notes\
```

每一段通常會產生這些檔案：

```text
xxx.md              Markdown 筆記草稿
xxx.transcript.txt  逐字稿
xxx.prompt.md       可以貼到 ChatGPT 或其他聊天工具的 prompt
```

WAV 音檔預設會在轉錄成功後刪除，避免佔空間。只有勾選「保留 WAV」時才會留下音檔。

## 第一次使用會比較久

第一次使用某個模型時，程式會自動下載 Whisper 模型到電腦裡。這是正常的，等下載完成後，下次就會快很多。

建議先用 `base` 模型，速度和準確度比較平衡。

## 常見問題

### 沒錄到聲音

請確認音效來源選的是有 `[Loopback]` 的裝置，而且課程影片正在播放。

### 轉錄很慢

可以改用 `tiny` 模型，速度會比較快，但準確度可能下降。

### 筆記內容不夠完整

可以把 `*.prompt.md` 的內容貼到 ChatGPT、Claude、Gemini 或其他聊天工具，請它幫你整理成更完整的文章。

### 想保留原始音檔

勾選「保留 WAV」。不勾的話，程式會在轉錄成功後自動刪除暫存音檔。

## 關於這個專案

Exam Scribe 目前內建 AWS SAA-C03 profile，但工具本身不是只給 AWS 用。之後可以加入更多考試 profile，讓它變成通用的備考筆記工具。

主要技術：

- Python
- Tkinter
- WASAPI loopback
- faster-whisper
- PyInstaller

開發者可以從原始碼自行修改 profile、UI 或打包流程；一般使用者只需要使用 `ExamScribe.exe`。
