"""螢幕框選翻譯：框住螢幕上的文字 → 內建 OCR（RapidOCR，免安裝語言包）辨識 → 翻譯成指定語言。

快捷鍵 Ctrl+Alt+T 隨時框選；Esc 或右鍵取消框選。
翻譯引擎：Google 翻譯（免金鑰）或 Claude（需環境變數 ANTHROPIC_API_KEY）。
"""
import ctypes
import ctypes.wintypes
import json
import os
import queue
import sys
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageGrab, ImageTk
from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 讓座標 = 實際像素
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# 打包成 exe 時設定檔放在 exe 旁邊
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "screen_translate_settings.json"

TARGET_LANGS = {
    "繁體中文": "zh-TW",
    "簡體中文": "zh-CN",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
    "Français": "fr",
    "Deutsch": "de",
    "Español": "es",
    "Português": "pt",
    "Italiano": "it",
    "Русский": "ru",
    "Tiếng Việt": "vi",
    "ไทย": "th",
    "Bahasa Indonesia": "id",
    "العربية": "ar",
    "हिन्दी": "hi",
}
ENGINES = ["Google 翻譯（免費）", "Claude（需 API 金鑰）"]
OCR_MODES = {
    "中文 / 日文 / 英文": None,  # PP-OCRv6 一個模型同時認繁簡中、日、英
    "韓文": "ko",
}
CLAUDE_MODEL = "claude-haiku-5-5"

HOTKEY_ID = 1
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_T = 0x54
WM_HOTKEY = 0x0312

DEFAULT_SETTINGS = {
    "target": "繁體中文",
    "engine": ENGINES[0],
    "ocr_lang": "中文 / 日文 / 英文",
    "hide_main": True,
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------- OCR ----------------

_engines = {}
_engine_lock = threading.Lock()


def get_engine(mode):
    with _engine_lock:
        if mode not in _engines:
            # 螢幕上的字不會倒過來，關掉方向分類（開著會把韓文轉反）
            params = {"Global.log_level": "error", "Global.use_cls": False}
            if mode == "ko":
                params.update({
                    "Rec.lang_type": LangRec.KOREAN,
                    "Rec.ocr_version": OCRVersion.PPOCRV5,
                    "Rec.model_type": ModelType.MOBILE,
                })
            _engines[mode] = RapidOCR(params=params)
        return _engines[mode]


# 不用空白分詞的文字（中、日）；韓文有空白所以不算
CJK = r"[぀-ヿ㐀-鿿＀-￯　-〿]"
FULLWIDTH = {",": "，", "!": "！", "?": "？", ";": "；", ":": "："}


def tidy_line(text):
    text = re.sub(rf"(?<={CJK})\s+(?={CJK})", "", text)
    # 中日文旁的半形標點轉全形並去掉多餘空白
    text = re.sub(rf"(?<={CJK})\s*([,!?;:])\s*", lambda m: FULLWIDTH[m.group(1)], text)
    return text.strip()


def run_ocr(img: Image.Image, mode):
    # 小字放大辨識率較好
    if img.height < 60:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    result = get_engine(mode)(np.array(img.convert("RGB")))
    lines = [tidy_line(t) for t in (result.txts or ()) if t.strip()]
    return join_lines(lines)


def join_lines(lines):
    """把被換行切斷的句子接回來：英文等用空白接，中日韓直接接；句尾標點才換行。"""
    out = ""
    for line in lines:
        if not out:
            out = line
        elif re.search(r"[.!?。！？:：;；]$", out):
            out += "\n" + line
        elif out.endswith("-") and re.match(r"[a-z]", line):
            out = out[:-1] + line
        elif re.search(CJK + "$", out) or re.match(CJK, line):
            out += line
        else:
            out += " " + line
    return out


# ---------------- 翻譯 ----------------

def translate_google(text, target):
    # 先用 clients5（較少被限流），失敗再用 gtx
    try:
        r = requests.post(
            "https://clients5.google.com/translate_a/t",
            params={"client": "dict-chrome-ex", "sl": "auto", "tl": target},
            data={"q": text},
            timeout=15,
        )
        r.raise_for_status()
        item = r.json()[0]
        return (item[0] if isinstance(item, list) else item), ""
    except Exception:
        pass
    r = requests.post(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t"},
        data={"q": text},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    translated = "".join(seg[0] for seg in data[0] if seg and seg[0])
    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else "?"
    return translated, detected


def translate_claude(text, target_name):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("沒有設定環境變數 ANTHROPIC_API_KEY，改用 Google 翻譯或先設定金鑰")
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=(
            f"You are a translator. Translate the user's text into {target_name}. "
            "The text came from OCR and may contain line-break or recognition errors; fix obvious ones silently. "
            "Output only the translation, nothing else."
        ),
        messages=[{"role": "user", "content": text}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip(), "Claude"


# ---------------- 全域快捷鍵 ----------------

def hotkey_thread(events: queue.Queue):
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_T):
        events.put(("hotkey_fail", None))
        return
    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            events.put(("hotkey", None))


def virtual_screen():
    m = ctypes.windll.user32.GetSystemMetrics
    return m(76), m(77), m(78), m(79)  # x, y, w, h


# ---------------- 框選視窗 ----------------

class Selector:
    def __init__(self, app):
        self.app = app
        vx, vy, vw, vh = virtual_screen()
        self.origin = (vx, vy)
        self.shot = ImageGrab.grab(bbox=(vx, vy, vx + vw, vy + vh), all_screens=True)

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{vw}x{vh}+{vx}+{vy}")

        dark = ImageEnhance.Brightness(self.shot).enhance(0.55)
        self.bg = ImageTk.PhotoImage(dark)
        self.bright = None
        self.canvas = tk.Canvas(self.win, width=vw, height=vh, highlightthickness=0, cursor="cross")
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.bg, anchor="nw")
        self.canvas.create_text(
            -vx + ctypes.windll.user32.GetSystemMetrics(0) // 2, 40 - vy,  # 主螢幕正上方
            text="拖曳框選要翻譯的文字　（Esc / 右鍵取消）",
            fill="white", font=("Microsoft JhengHei UI", 16, "bold"),
        )
        self.rect = None
        self.patch = None
        self.start = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", lambda e: self.close())
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()
        self.win.after(50, self.win.focus_force)

    def box(self, e):
        x0, y0 = self.start
        return min(x0, e.x), min(y0, e.y), max(x0, e.x), max(y0, e.y)

    def on_press(self, e):
        self.start = (e.x, e.y)

    def on_drag(self, e):
        if not self.start:
            return
        x0, y0, x1, y1 = self.box(e)
        if x1 - x0 > 1 and y1 - y0 > 1:
            self.bright = ImageTk.PhotoImage(self.shot.crop((x0, y0, x1, y1)))
            if self.patch:
                self.canvas.coords(self.patch, x0, y0)
                self.canvas.itemconfigure(self.patch, image=self.bright)
            else:
                self.patch = self.canvas.create_image(x0, y0, image=self.bright, anchor="nw")
        if self.rect:
            self.canvas.coords(self.rect, x0, y0, x1, y1)
            self.canvas.tag_raise(self.rect)
        else:
            self.rect = self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ff3b30", width=2)

    def on_release(self, e):
        if not self.start:
            return
        x0, y0, x1, y1 = self.box(e)
        self.close()
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        crop = self.shot.crop((x0, y0, x1, y1))
        ox, oy = self.origin
        self.app.process(crop, (x0 + ox, y0 + oy, x1 + ox, y1 + oy))

    def close(self):
        self.win.destroy()
        self.app.selector_closed()


# ---------------- 結果視窗 ----------------

class ResultWindow:
    def __init__(self, app, region):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("翻譯結果")
        self.win.attributes("-topmost", True)
        self.win.bind("<Escape>", lambda e: self.win.destroy())

        font = ("Microsoft JhengHei UI", 11)
        frm = ttk.Frame(self.win, padding=8)
        frm.pack(fill="both", expand=True)

        self.src_label = ttk.Label(frm, text="原文（可修改後按「重新翻譯」）")
        self.src_label.pack(anchor="w")
        self.src = tk.Text(frm, height=6, wrap="word", font=font, undo=True)
        self.src.pack(fill="both", expand=True, pady=(2, 6))

        self.dst_label = ttk.Label(frm, text="譯文")
        self.dst_label.pack(anchor="w")
        self.dst = tk.Text(frm, height=8, wrap="word", font=font, background="#f4f8ff")
        self.dst.pack(fill="both", expand=True, pady=(2, 6))

        bar = ttk.Frame(frm)
        bar.pack(fill="x")
        self.status = ttk.Label(bar, text="辨識中…", foreground="#666")
        self.status.pack(side="left")
        ttk.Button(bar, text="關閉", command=self.win.destroy).pack(side="right")
        ttk.Button(bar, text="複製譯文", command=self.copy).pack(side="right", padx=4)
        ttk.Button(bar, text="重新翻譯", command=self.retranslate).pack(side="right")

        self.place(region)

    def place(self, region):
        w, h = 520, 440
        x0, y0, x1, y1 = region
        vx, vy, vw, vh = virtual_screen()
        x = min(max(x0, vx), vx + vw - w)
        y = y1 + 10 if y1 + 10 + h < vy + vh else max(vy, y0 - h - 40)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.lift()
        self.win.focus_force()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def set_text(self, widget, text):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def copy(self):
        self.win.clipboard_clear()
        self.win.clipboard_append(self.dst.get("1.0", "end").strip())
        self.status.config(text="已複製")

    def retranslate(self):
        text = self.src.get("1.0", "end").strip()
        if text:
            self.status.config(text="翻譯中…")
            self.app.start_translate(self, text)


# ---------------- 主程式 ----------------

class App:
    def __init__(self):
        self.settings = load_settings()
        self.events = queue.Queue()
        self.selecting = False

        self.root = tk.Tk()
        self.root.title("螢幕框選翻譯")
        self.root.resizable(False, False)
        style = ttk.Style()
        style.configure(".", font=("Microsoft JhengHei UI", 10))

        frm = ttk.Frame(self.root, padding=12)
        frm.pack()

        ttk.Label(frm, text="翻譯成").grid(row=0, column=0, sticky="w", pady=3)
        self.target = ttk.Combobox(frm, values=list(TARGET_LANGS), state="readonly", width=24)
        self.target.set(self.settings["target"] if self.settings["target"] in TARGET_LANGS else "繁體中文")
        self.target.grid(row=0, column=1, pady=3)

        ttk.Label(frm, text="翻譯引擎").grid(row=1, column=0, sticky="w", pady=3)
        self.engine = ttk.Combobox(frm, values=ENGINES, state="readonly", width=24)
        self.engine.set(self.settings["engine"] if self.settings["engine"] in ENGINES else ENGINES[0])
        self.engine.grid(row=1, column=1, pady=3)

        ttk.Label(frm, text="辨識語言").grid(row=2, column=0, sticky="w", pady=3)
        self.ocr = ttk.Combobox(frm, values=list(OCR_MODES), state="readonly", width=24)
        self.ocr.set(self.settings["ocr_lang"] if self.settings["ocr_lang"] in OCR_MODES else next(iter(OCR_MODES)))
        self.ocr.grid(row=2, column=1, pady=3)

        self.hide_main = tk.BooleanVar(value=self.settings["hide_main"])
        ttk.Checkbutton(frm, text="框選時隱藏這個視窗", variable=self.hide_main,
                        command=self.save).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)

        ttk.Button(frm, text="框選翻譯  (Ctrl+Alt+T)", command=self.begin_select).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2), ipady=4)
        self.hint = ttk.Label(frm, text="辨識模型載入中…", foreground="#777",
                              font=("Microsoft JhengHei UI", 8))
        self.hint.grid(row=5, column=0, columnspan=2, sticky="w")

        for cb in (self.target, self.engine, self.ocr):
            cb.bind("<<ComboboxSelected>>", lambda e: self.save())

        threading.Thread(target=hotkey_thread, args=(self.events,), daemon=True).start()
        threading.Thread(target=self.warm_up, daemon=True).start()
        self.root.after(100, self.poll)

    def warm_up(self):
        # 先載入模型，第一次框選才不會等
        try:
            get_engine(OCR_MODES[self.ocr.get()])
            self.ui(lambda: self.hint.config(text="就緒：按 Ctrl+Alt+T 框選"))
        except Exception as e:
            self.ui(lambda: self.hint.config(text=f"OCR 模型載入失敗：{e}", foreground="#c00"))

    def save(self):
        self.settings.update(
            target=self.target.get(), engine=self.engine.get(),
            ocr_lang=self.ocr.get(), hide_main=self.hide_main.get(),
        )
        save_settings(self.settings)

    def poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "hotkey":
                    self.begin_select()
                elif kind == "hotkey_fail":
                    self.hint.config(text="Ctrl+Alt+T 被其他程式佔用，請用按鈕框選", foreground="#c00")
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def ui(self, fn):
        """從背景執行緒安全地更新介面。"""
        self.events.put(("call", fn))

    def begin_select(self):
        if self.selecting:
            return
        self.selecting = True
        self.was_visible = self.root.state() == "normal"
        if self.hide_main.get() and self.was_visible:
            self.root.withdraw()
            self.root.after(200, lambda: Selector(self))
        else:
            Selector(self)

    def selector_closed(self):
        self.selecting = False
        if self.hide_main.get() and self.was_visible:
            self.root.deiconify()

    def process(self, img, region):
        rw = ResultWindow(self, region)
        mode = OCR_MODES[self.ocr.get()]

        def work():
            try:
                text = run_ocr(img, mode)
            except Exception as e:
                self.ui(lambda: rw.alive() and rw.status.config(text=f"OCR 失敗：{e}"))
                return
            if not text:
                self.ui(lambda: rw.alive() and rw.status.config(text="沒辨識到文字，試著換「辨識語言」或框大一點"))
                return
            self.ui(lambda: rw.alive() and (rw.set_text(rw.src, text), rw.status.config(text="翻譯中…")))
            self.translate(rw, text)

        threading.Thread(target=work, daemon=True).start()

    def start_translate(self, rw, text):
        threading.Thread(target=self.translate, args=(rw, text), daemon=True).start()

    def translate(self, rw, text):
        target_name = self.target.get()
        try:
            if self.engine.get() == ENGINES[1]:
                result, detected = translate_claude(text, target_name)
            else:
                result, detected = translate_google(text, TARGET_LANGS[target_name])
            status = f"{detected} → {target_name}" if detected else f"已翻譯成 {target_name}"
        except Exception as e:
            result, status = "", f"翻譯失敗：{e}"
        self.ui(lambda: rw.alive() and (rw.set_text(rw.dst, result), rw.status.config(text=status)))

    def run(self):
        self.root.mainloop()


def selftest():
    """螢幕翻譯.exe --selftest：用內建範例檢查 OCR 與翻譯，結果寫到 selftest.txt。"""
    from PIL import ImageDraw, ImageFont
    samples = [
        (None, "今日はいい天気ですね。", "msgothic.ttc"),
        (None, "今天天氣很好，我們去散步吧。", "msjh.ttc"),
        (None, "The quick brown fox jumps.", "arial.ttf"),
        ("ko", "안녕하세요 반갑습니다", "malgun.ttf"),
    ]
    out = []
    for mode, text, font in samples:
        img = Image.new("RGB", (560, 60), "white")
        ImageDraw.Draw(img).text((10, 12), text, fill="black",
                                 font=ImageFont.truetype(f"C:/Windows/Fonts/{font}", 26))
        try:
            got = run_ocr(img, mode)
            tr = translate_google(got, "zh-TW")[0] if got else ""
            out.append(f"{'OK ' if got else 'FAIL'} {text} -> {got} -> {tr}")
        except Exception as e:
            out.append(f"FAIL {text} -> {e!r}")
    (APP_DIR / "selftest.txt").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        App().run()
