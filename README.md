# 螢幕框選翻譯 screen-translate

框住螢幕上的文字，自動辨識並翻譯成你事先選好的語言。Windows 用。

- 按 **Ctrl+Alt+T**（或主視窗按鈕）→ 拖曳框選文字 → 旁邊跳出原文與譯文
- 辨識內建 [RapidOCR](https://github.com/RapidAI/RapidOCR)，**不用安裝 Windows 語言包**
  - 繁中、簡中、日文、英文：同一個模型，直接框就好
  - 韓文：「辨識語言」選「韓文」
- 翻譯成 16 種語言（繁中、簡中、英、日、韓、法、德、西、葡、義、俄、越、泰、印尼、阿拉伯、印地）
- 翻譯引擎：Google 翻譯（免費、免金鑰）或 Claude（需設定環境變數 `ANTHROPIC_API_KEY`）
- 原文辨識有誤可直接修改再按「重新翻譯」；「複製譯文」一鍵複製
- Esc 或右鍵取消框選

## 直接使用（免安裝 Python）

1. 到 [Releases](../../releases) 下載 `螢幕翻譯.zip`
2. 解壓縮，執行資料夾裡的 `螢幕翻譯.exe`（整個資料夾要一起留著）
3. 第一次執行若出現「Windows 已保護您的電腦」，按「其他資訊」→「仍要執行」

辨識在本機進行，翻譯需要連網（文字會送到 Google 翻譯或 Claude）。

## 從原始碼執行

需要 Python 3.10 以上。

```bash
pip install -r requirements.txt
python screen_translate.py
```

或雙擊 `啟動螢幕翻譯.bat`。

第一次選「韓文」辨識時會自動下載韓文模型（約 13 MB）。

## 自己打包成 exe

```bash
pip install pyinstaller
python -c "from rapidocr import RapidOCR, LangRec, OCRVersion, ModelType; RapidOCR(params={'Rec.lang_type': LangRec.KOREAN, 'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE})"
pyinstaller --noconfirm --noconsole --onedir --name 螢幕翻譯 --collect-data rapidocr --collect-submodules rapidocr screen_translate.py
```

第二行先把韓文模型下載進 rapidocr 套件，打包時才會一起帶進去。建議在只裝了 requirements 的乾淨 venv 裡打包，exe 比較小。

打包完可用 `螢幕翻譯.exe --selftest` 檢查：會用內建範例跑辨識和翻譯，結果寫到 exe 旁的 `selftest.txt`。
