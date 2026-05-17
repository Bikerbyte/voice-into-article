# Exam Scribe

Exam Scribe 是一個本機優先的備考筆記工具，可以錄下 Windows 電腦正在播放的課程聲音，轉成逐字稿，並產生考試導向的 Markdown 筆記草稿。

目前的核心流程：

- 透過 Windows WASAPI loopback 錄下電腦喇叭聲音
- 錄音不中斷時也能手動或自動分段轉錄
- 使用 `faster-whisper` 在本機轉錄，不需要 API key
- 依照可設定的 exam profile 產生備考筆記
- 內建 AWS SAA-C03 profile，但工具本身不是綁定 AWS
- 預設轉錄成功後刪除暫存 WAV，避免音檔佔用空間

## 快速開始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
exam-scribe demo
```

Demo 會在 `workspace/notes/` 裡產生範例逐字稿與 Markdown 筆記。

## 桌面 UI

如果不想每次都輸入指令，可以直接開桌面工具：

```powershell
exam-scribe-ui
```

或：

```powershell
exam-scribe ui
```

UI 可以做到：

- 選擇電腦聲音來源
- 選擇考試 profile
- 輸入筆記標題
- 按下「開始錄音」
- 錄音途中按「轉錄目前片段」，目前累積的聲音會切出來轉錄，後面的聲音會繼續錄
- 勾選「自動每 N 秒轉錄」後，可以固定每段例如 30 秒自動切片處理
- 按下「停止錄音」後，最後剩下的片段會自動送出處理
- 使用 Whisper 本機轉錄
- 產生 Markdown 備考筆記草稿
- 產生可貼到聊天工具的 prompt
- 預設刪除暫存 WAV
- 開啟筆記、開啟 prompt、複製 prompt、開啟資料夾

預設輸出位置：

```text
workspace/notes/  筆記、逐字稿、prompt；WAV 預設處理成功後刪除
```

每段輸出會放在同一個資料夾，方便丟到 GitHub Pages 或部落格專案：

```text
20260517-lecture-part-001.md              Markdown 筆記草稿
20260517-lecture-part-001.transcript.txt  逐字稿
20260517-lecture-part-001.prompt.md       可貼到聊天工具的 prompt
20260517-lecture-part-001.wav             只有勾選「保留 WAV」才會留下
```

用 `exam-scribe-ui` 開發版啟動時，預設會使用專案內的 `workspace/`。用打包後的 `ExamScribe.exe` 啟動時，預設會使用：

```text
C:\Users\<你的使用者名稱>\Documents\ExamScribe\
```

第一次使用某個 Whisper 模型時，會下載模型到 Hugging Face 快取。建議先用 `base`，速度與準確度比較平衡；想更快可以用 `tiny`，想更準可以用 `small`。

### 連續錄音與分段轉錄

新的 UI 工作流適合一邊看課程一邊整理筆記：

1. 按「開始錄音」後，Exam Scribe 會持續錄電腦正在播放的聲音。
2. 看到一個小段落結束時，按「轉錄目前片段」。這只會把目前累積的聲音切出來處理，不會停止錄音。
3. 如果想少按按鈕，可以勾選「自動每 N 秒轉錄」，例如填 `30` 就會約每 30 秒切出一段。
4. 按「停止錄音」時，尚未切出的最後一段會自動轉錄。

每個片段都會各自產生逐字稿、prompt 和 Markdown 草稿。WAV 仍然預設在轉錄成功後刪除，除非勾選「保留 WAV」。

## Windows 執行檔

已包好的程式在：

```text
dist/ExamScribe/ExamScribe.exe
```

請搬移整個 `dist/ExamScribe/` 資料夾，不要只單獨搬 `ExamScribe.exe`。這是因為本機轉錄需要一整組原生函式庫。

重新打包：

```powershell
.\scripts\build_exe.ps1
```

## 錄下系統音效

播放課程影片後，錄下電腦目前播放的聲音：

```powershell
exam-scribe devices
exam-scribe record --minutes 5 --out workspace/notes/aws-session-01.wav
```

如果預設裝置不是你正在聽課的喇叭或耳機，可以指定裝置 index：

```powershell
exam-scribe record --seconds 30 --device-index 17 --out workspace/notes/test.wav
```

這只錄電腦播放聲音，不會錄麥克風。

## 本機轉錄

預設使用 `faster-whisper` 本機轉錄，不需要 API key：

```powershell
exam-scribe transcribe workspace/notes/aws-session-01.wav `
  --provider local `
  --model base `
  --language en `
  --delete-audio `
  --out workspace/notes/aws-session-01.transcript.txt
```

說明：

- `--model base`：使用 Whisper base 模型
- `--language en`：提示音訊是英文課程；可省略讓 Whisper 自動偵測
- `--delete-audio`：轉錄成功後刪除輸入音檔

## 無 API Key 工作流

### 方式 A：本機轉錄後產生 prompt

```powershell
exam-scribe record --seconds 60 --device-index 17 --out workspace/notes/aws-session-01.wav
exam-scribe transcribe workspace/notes/aws-session-01.wav `
  --provider local `
  --model base `
  --language en `
  --delete-audio `
  --out workspace/notes/aws-session-01.transcript.txt
exam-scribe prompt --transcript workspace/notes/aws-session-01.transcript.txt `
  --profile aws-saa-c03 `
  --title "VPC Endpoint and PrivateLink" `
  --out workspace/notes/vpc-endpoint.prompt.md
```

接著把 `workspace/notes/vpc-endpoint.prompt.md` 的內容貼到 ChatGPT、Codex、Claude、Gemini 或其他聊天工具。

### 方式 B：直接用既有字幕或逐字稿

如果課程有字幕，可以把字幕存成文字檔，再產生 prompt：

```powershell
exam-scribe prompt --transcript workspace/notes/aws-session-01.transcript.txt `
  --profile aws-saa-c03 `
  --title "VPC Endpoint and PrivateLink" `
  --out workspace/notes/vpc-endpoint.prompt.md
```

### 方式 C：只用本機模板產生草稿

這不使用任何 LLM，適合快速草稿與 smoke test：

```powershell
exam-scribe note workspace/notes/aws-session-01.transcript.txt `
  --profile aws-saa-c03 `
  --title "VPC Endpoint and PrivateLink" `
  --out workspace/notes/vpc-endpoint.md
```

本機草稿會包含：

- 核心觀念
- 考試會怎麼問
- 易混淆選項
- 情境題判斷規則
- 記憶口訣
- 需要查官方文件
- 原始逐字稿

## 一次跑完整流程

```powershell
exam-scribe run --minutes 10 --profile aws-saa-c03 --title "IAM Policies"
```

這會錄音、轉錄、產生 Markdown 筆記，並預設刪除暫存 WAV。

英文課程可加上語言提示：

```powershell
exam-scribe run --minutes 10 `
  --profile aws-saa-c03 `
  --title "IAM Policies" `
  --transcribe-language en
```

如果想保留錄音檔：

```powershell
exam-scribe run --minutes 10 --keep-audio
```

## Profiles

Profile 用來定義不同考試的專有名詞、修正規則、標籤與筆記章節。內建 profile 在：

```text
src/exam_scribe/profiles/
```

列出內建 profiles：

```powershell
exam-scribe profiles
```

範例 profile：

```toml
id = "ccna"
name = "Cisco CCNA"
language = "zh-TW"
tags = ["ccna", "networking"]
glossary = ["VLAN", "OSPF", "BGP", "STP"]
sections = [
  "核心觀念",
  "考試會怎麼問",
  "易混淆選項",
  "情境題判斷規則",
  "記憶口訣",
  "需要查官方文件",
]

[corrections]
"v land" = "VLAN"
"oh SPF" = "OSPF"
```

## 模型快取位置

`faster-whisper` 會把模型下載到 Hugging Face 快取：

```text
C:\Users\<你的使用者名稱>\.cache\huggingface\hub\
```

刪掉對應模型資料夾可以釋放空間；下次使用同一模型時會重新下載。
