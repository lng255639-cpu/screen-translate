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

### 鎖定區域（適合遊戲對話框、字幕）

1. 主視窗按「框選鎖定區域」，框一次要固定翻譯的位置（會先翻譯一次）
2. 之後在任何程式裡按 **Q**（翻譯鍵），馬上辨識並翻譯那個位置，結果顯示在固定的「鎖定翻譯」視窗
3. 翻譯鍵可改：點主視窗「翻譯鍵」按鈕再按想用的鍵（例如 F2）

- 按鍵不會被吃掉：在遊戲裡按 Q，遊戲一樣收得到
- 按住 Ctrl / Alt 時、或正在操作本程式視窗時不觸發
- 鎖定框（紅色虛線）和鎖定翻譯視窗不會被截進辨識畫面，蓋到鎖定區域也沒關係
- 鎖定翻譯視窗不搶焦點，打遊戲不會被切出來
- 鎖定位置和翻譯鍵會記住，下次開程式還在；不用時按「解除鎖定」
- 打字時翻譯鍵也會觸發，常打字的話建議改成 F 鍵
- 遊戲若以系統管理員身分執行，本程式也要用系統管理員身分開，才收得到按鍵；全螢幕獨佔模式的遊戲請改用「無邊框視窗」

## 直接使用（免安裝 Python）

1. 到 [Releases](../../releases) 下載 `screen-translate-win64.zip`
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
