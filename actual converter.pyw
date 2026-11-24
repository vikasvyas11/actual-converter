import ctypes
from ctypes import wintypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import queue
import random
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from converter import Cancelled, IMAGE_INPUTS, VIDEO_INPUTS, IMAGES, VIDEOS, LOSSY, convert, extension

PAPER, SURFACE, SUBTLE = "#ffffff", "#fafaf9", "#f4f4f1"
INK, MUTED, LINE = "#000000", "#72726d", "#d9d9d5"
SPECTRUM = ("#ff8705", "#ff8df2", "#6385ff", "#37d7fa")
SPARKS = ("#ff8705", "#ff8df2", "#6385ff", "#37d7fa", "#fba647", "#fca6f3", "#92aeff", "#96e7f9")
BRICK_TINTS = ("#e2e0d9", "#fba647", "#fca6f3", "#92aeff", "#96e7f9")
PASTEL_BANDS = ("#fbd8b0", "#fbd0d0", "#fbcce1", "#f1cde9", "#e2cff1", "#d0d0f6", "#c6d5fa", "#c4defa", "#c2e7f9", "#c0f0f9")
FONT, MONO = "Segoe UI", "Consolas"

# 8x8 pixel swap-arrows glyph (⇄)
SWAP_CELLS = (
    (1, 5),
    (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6),
    (3, 5),
    (4, 2),
    (5, 1), (5, 2), (5, 3), (5, 4), (5, 5), (5, 6),
    (6, 2),
)


def label(parent, text, size=10, fg=INK, bg=None, font_family=FONT, weight="normal", **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg or parent["bg"],
                    font=(font_family, size, weight), bd=0, **kw)


def button(parent, text, command, bg=SUBTLE, fg=INK, border=LINE, mono=False, **kw):
    dark = bg == INK
    return tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground="#262624" if dark else "#eaeae5",
        activeforeground=PAPER if dark else INK,
        disabledforeground="#8c8c88" if dark else "#9a9a94",
        relief="flat", overrelief="flat", bd=0,
        highlightthickness=1, highlightbackground=border if not dark else INK, highlightcolor=SPECTRUM[2],
        cursor="hand2", font=(MONO if mono else FONT, 9 if mono else 10, "bold"),
        padx=12, pady=6, **kw,
    )


def accept_drops(root, add):
    """Use Explorer's standard WM_DROPFILES interface; keep the callback alive with the window."""
    user32, shell = ctypes.windll.user32, ctypes.windll.shell32
    hwnd = root.winfo_id()
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    hwnd = user32.GetParent(hwnd) or hwnd
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    setter = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
    setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    setter.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    shell.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell.DragFinish.argtypes = [wintypes.HANDLE]

    @callback_type
    def dispatch(window, message, wp, lp):
        if message == 0x0233:
            paths = []
            try:
                for idx in range(shell.DragQueryFileW(wp, 0xffffffff, None, 0)):
                    size = shell.DragQueryFileW(wp, idx, None, 0) + 1
                    buf = ctypes.create_unicode_buffer(size)
                    shell.DragQueryFileW(wp, idx, buf, size)
                    paths.append(buf.value)
            finally:
                shell.DragFinish(wp)
            root.after_idle(add, paths)
            return 0
        return user32.CallWindowProcW(previous, window, message, wp, lp)

    previous = setter(hwnd, -4, ctypes.cast(dispatch, ctypes.c_void_p))
    if not previous:
        return
    shell.DragAcceptFiles(hwnd, True)
    root._drop_callback = dispatch


class Desk:
    def __init__(self, root):
        self.root = root
        # Fit the desk on compact laptop displays while respecting the Windows DPI setting.
        self.scale = min(float(root.tk.call("tk", "scaling")) * .75,
                         (root.winfo_screenwidth()-40)/900, (root.winfo_screenheight()-90)/660)
        root.tk.call("tk", "scaling", self.scale * 4/3)
        px = lambda value: round(value * self.scale)
        self.px = px
        self.jobs = {}
        self.events = queue.Queue()
        self.cancel = None
        self.closing = False
        self.directory = None
        self.last = None
        self.motion = False
        self._logo_sparks = []
        self._logo_pointer = None
        self._logo_after = None
        self._logo_last = 0.0
        self._logo_phase = 0
        self._hero_cells = {}
        self._hero_after = None
        self._hero_bucket = None
        self._hero_size = (0, 0)

        root.title("actual converter")
        root.iconbitmap(str(Path(__file__).with_name("actual.ico")))
        root.configure(bg=PAPER)
        width = min(px(990), root.winfo_screenwidth()-40)
        height = min(px(680), root.winfo_screenheight()-90)
        x = max(0, (root.winfo_screenwidth()-width)//2)
        y = max(0, (root.winfo_screenheight()-height-60)//2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(px(760), px(610))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", background=PAPER, fieldbackground=PAPER, foreground=INK,
                        borderwidth=0, rowheight=px(32), font=(FONT, 10))
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.map("Treeview", background=[("selected", "#edf1ff")], foreground=[("selected", INK)])
        style.configure("TCombobox", padding=6, fieldbackground=PAPER, bordercolor=LINE, arrowsize=14)
        style.map("TCombobox", fieldbackground=[("readonly", PAPER)])

        header = tk.Frame(root, bg=PAPER, padx=24, pady=8)
        header.grid(row=0, column=0, sticky="ew")
        self.logo_canvas = tk.Canvas(header, bg=PAPER, width=px(300), height=px(40),
                                     highlightthickness=0, cursor="hand2")
        self.logo_canvas.pack(side="left")
        self.logo_canvas.bind("<Motion>", self._on_logo_motion)
        self.logo_canvas.bind("<Leave>", self._on_logo_leave)
        self._draw_logo()

        tk.Label(header, text="WINDOWS  ·  V1.0", bg=INK, fg=PAPER,
                 font=(MONO, 9, "bold"), padx=9, pady=4).pack(side="right")
        tk.Frame(root, bg=LINE, height=1).grid(row=1, column=0, sticky="ew")

        body = tk.Frame(root, bg=PAPER, padx=24, pady=14)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        top_row = tk.Frame(body, bg=PAPER)
        top_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        tk.Label(top_row, text="Conversion desk", font=("Georgia", 26), bg=PAPER, fg=INK).pack(side="left")
        tk.Label(top_row, text="LOCAL · OFFLINE · ZERO UPLOADS", font=(MONO, 8, "bold"),
                 bg=SUBTLE, fg=MUTED, padx=8, pady=4).pack(side="right", pady=6)

        left = tk.Frame(body, bg=PAPER)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=2)

        self.hero = tk.Canvas(left, bg=SURFACE, height=px(180), width=px(280),
                              highlightthickness=1, highlightbackground=LINE, cursor="hand2")
        self.hero.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.hero.bind("<Configure>", self.draw_hero)
        self.hero.bind("<Motion>", self._on_hero_motion)
        self.hero.bind("<Leave>", self._on_hero_leave)
        self.hero.bind("<Button-1>", lambda e: self.browse())
        self.browse_button = button(self.hero, "+  CHOOSE FILES", self.browse, bg=INK, fg=PAPER, mono=True)

        box = tk.Frame(left, bg=PAPER, highlightbackground=LINE, highlightthickness=1, padx=14, pady=10)
        box.grid(row=1, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        qhead = tk.Frame(box, bg=PAPER)
        qhead.grid(sticky="ew")
        self.count = label(qhead, "FILE QUEUE  ·  0", 9, font_family=MONO, weight="bold")
        self.count.pack(side="left")
        self.clear = button(qhead, "CLEAR", self.clear_queue, bg=PAPER, mono=True)
        self.clear.pack(side="right")
        rows = tk.Frame(box, bg=PAPER)
        rows.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.tree = ttk.Treeview(rows, columns=("type", "name", "status"), show="tree", height=2, selectmode="extended")
        self.tree.column("#0", width=0, stretch=False)
        for name, col_width in (("type", 54), ("name", 90), ("status", 92)):
            self.tree.column(name, width=col_width, minwidth=25, stretch=name == "name")
        scroll = ttk.Scrollbar(rows, orient="vertical", command=self.tree.yview)

        def scroll_range(first, last):
            scroll.set(first, last)
            if float(first) > 0 or float(last) < 1:
                scroll.pack(side="right", fill="y", before=self.tree)
            else:
                scroll.pack_forget()

        self.tree.configure(yscrollcommand=scroll_range)
        self.tree.pack(fill="both", expand=True)
        self.empty = label(rows, "Your files will appear here.", fg=MUTED)
        self.tree.bind("<Double-1>", self.inspect_row)
        self.tree.bind("<Return>", self.inspect_row)
        self.tree.bind("<Delete>", lambda e: self.remove(self.tree.selection()))

        settings = tk.Frame(body, bg=SURFACE, width=px(286), highlightbackground=LINE, highlightthickness=1)
        settings.grid(row=1, column=1, sticky="nsew")
        settings.grid_propagate(False)
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(0, weight=1)
        fields = tk.Frame(settings, bg=SURFACE, padx=16, pady=14)
        fields.grid(sticky="nsew")
        label(fields, "OUTPUT", 8, fg=MUTED, font_family=MONO, weight="bold").pack(anchor="w")
        tk.Label(fields, text="Output settings", bg=SURFACE, fg=INK, font=("Georgia", 17)).pack(anchor="w", pady=(2, 10))
        modes = tk.Frame(fields, bg=LINE, padx=1, pady=1)
        modes.pack(fill="x")
        self.tabs = []
        for val, name in enumerate(("IMAGE", "VIDEO")):
            tab = button(modes, name, lambda v=val: self.mode(bool(v)), mono=True)
            tab.pack(side="left", fill="x", expand=True)
            self.tabs.append(tab)
        ramp = tk.Canvas(fields, bg=SURFACE, height=2, highlightthickness=0)
        ramp.pack(fill="x", pady=(0, 2))
        ramp.bind("<Configure>", lambda e, c=ramp: self._draw_ramp(c, e.width, e.height))

        self.fmt = self.combo(fields, "FORMAT")
        self.preset = self.combo(fields, "PRESET")
        self.fmt.bind("<<ComboboxSelected>>", lambda e: self.presets())
        self.preset.bind("<<ComboboxSelected>>", lambda e: self.hint())
        label(fields, "SAVE TO", 9, font_family=MONO, weight="bold").pack(anchor="w", pady=(10, 3))
        dest = tk.Frame(fields, bg=SURFACE)
        dest.pack(fill="x")
        self.change = button(dest, "CHANGE", self.choose_folder, bg=PAPER, mono=True)
        self.change.pack(side="right")
        self.folder_name = label(dest, "Next to original", fg=MUTED, anchor="w")
        self.folder_name.pack(side="left", fill="x", expand=True)
        self.reset = button(fields, "Use original folder", lambda: self.set_folder(None), bg=PAPER)
        self.note = label(fields, "", 9, fg=MUTED, justify="left", wraplength=px(240))
        self.note.pack(anchor="w", pady=(10, 0))
        self.action = button(settings, "CONVERT FILES  →", self.start, bg=INK, fg=PAPER, mono=True)
        self.action.grid(row=1, column=0, sticky="ew", padx=16, pady=(3, 14), ipady=4)

        tk.Frame(root, bg=LINE, height=1).grid(row=3, column=0, sticky="ew")
        footer = tk.Frame(root, bg=SUBTLE, padx=24, pady=6)
        footer.grid(row=4, column=0, sticky="ew")
        self.dot = label(footer, "■", 8, fg=SPECTRUM[2], font_family=MONO)
        self.dot.pack(side="left")
        self.status = label(footer, "Ready", 9, font_family=MONO, anchor="w")
        self.status.pack(side="left", padx=8, fill="x", expand=True)
        self.reveal = button(footer, "SHOW OUTPUT", self.show_output, bg=PAPER, mono=True)
        self.mode(False)
        self.refresh()
        root.bind("<Control-o>", lambda e: self.browse())
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.update_idletasks()
        accept_drops(root, self.add)

    @staticmethod
    def combo(parent, title):
        label(parent, title, 9, font_family=MONO, weight="bold").pack(anchor="w", pady=(10, 3))
        combo = ttk.Combobox(parent, state="readonly", font=(FONT, 10), width=16)
        combo.pack(fill="x")
        return combo

    @staticmethod
    def _draw_ramp(canvas, width, height):
        canvas.delete("all")
        if width <= 0:
            return
        seg = width / len(SPECTRUM)
        for i, color in enumerate(SPECTRUM):
            canvas.create_rectangle(round(i * seg), 0, round((i + 1) * seg) + 1, height, fill=color, outline="")

    def _draw_logo(self):
        if self.closing:
            return
        c = self.logo_canvas
        try:
            c.delete("all")
        except tk.TclError:
            return
        now = time.monotonic()
        self._logo_sparks = [s for s in self._logo_sparks if s[5] > now]
        for x, y, w, h, color, _ in self._logo_sparks:
            c.create_rectangle(x, y, x + w, y + h, fill=color, outline="")

        size = max(24, self.px(32))
        x0, y0 = self.px(4), self.px(4)
        c.create_rectangle(x0, y0, x0 + size, y0 + size, fill=INK, outline="")
        cell = size / 10.0
        pad = size / 10.0
        active = self._logo_pointer is not None
        for r, col in SWAP_CELLS:
            dx = dy = 0
            color = SPECTRUM[min(3, (col * 4) // 8)]
            if active:
                px_x = x0 + pad + col * cell + cell / 2
                px_y = y0 + pad + r * cell + cell / 2
                dist = ((px_x - self._logo_pointer[0]) ** 2 + (px_y - self._logo_pointer[1]) ** 2) ** 0.5
                if dist < size * 1.1:
                    color = SPECTRUM[(col + self._logo_phase) % len(SPECTRUM)]
                    if dist < size * 0.55 and ((col + r + self._logo_phase) % 5 == 0):
                        dx = 0.75 if r < 4 else -0.75
                        dy = -0.5 if (col % 2 == 0) else 0.5
            rx = x0 + pad + (col + dx) * cell
            ry = y0 + pad + (r + dy) * cell
            c.create_rectangle(rx, ry, rx + cell - 0.5, ry + cell - 0.5, fill=color, outline="")

        c.create_text(x0 + size + self.px(11), y0 + size / 2, text="actual converter",
                      anchor="w", fill=INK, font=(FONT, 15, "bold"))

    def _on_logo_motion(self, event):
        self._logo_pointer = (event.x, event.y)
        now = time.monotonic()
        if now - self._logo_last >= 0.04:
            self._logo_last = now
            self._logo_phase = (self._logo_phase + 1) % 100
            for _ in range(2):
                if len(self._logo_sparks) >= 20:
                    self._logo_sparks.pop(0)
                sx = round((event.x + random.randint(-14, 14)) / 4) * 4
                sy = round((event.y + random.randint(-10, 10)) / 4) * 4
                wide = random.random() > 0.35
                self._logo_sparks.append((
                    sx, sy, 6 if wide else 4, 3 if wide else 4,
                    random.choice(SPARKS) if random.random() > 0.15 else INK,
                    now + random.uniform(0.18, 0.34),
                ))
        self._draw_logo()
        if self._logo_after is None:
            self._logo_after = self.root.after(45, self._tick_logo)

    def _on_logo_leave(self, _event):
        self._logo_pointer = None
        if self._logo_after is None and self._logo_sparks:
            self._logo_after = self.root.after(45, self._tick_logo)
        else:
            self._draw_logo()

    def _tick_logo(self):
        self._logo_after = None
        if self.closing:
            return
        self._draw_logo()
        if self._logo_pointer is not None or self._logo_sparks:
            self._logo_after = self.root.after(45, self._tick_logo)

    def draw_hero(self, event):
        c = self.hero
        c.delete("all")
        w, h = event.width, event.height
        self._hero_size = (w, h)
        factor = self.scale
        bw = max(28, round(56 * factor))
        bh = max(14, round(28 * factor))
        for row, y in enumerate(range(0, h + bh, bh)):
            c.create_line(0, y, w, y, fill="#eaeae5")
            offset = (bw // 2) if (row % 2) else 0
            for x in range(offset, w + bw, bw):
                c.create_line(x, y, x, min(h, y + bh), fill="#eaeae5")

        pad_x = max(12, round(18 * factor))
        pad_y = max(10, round(14 * factor))
        px1, py1 = pad_x, pad_y
        px2, py2 = max(px1 + 80, w - pad_x), max(py1 + 80, h - pad_y)
        pw, ph = px2 - px1, py2 - py1

        band_h = ph / len(PASTEL_BANDS)
        for i, color in enumerate(PASTEL_BANDS):
            by1 = py1 + round(i * band_h)
            by2 = py1 + round((i + 1) * band_h)
            c.create_rectangle(px1, by1, px2, by2, fill=color, outline="", tags="plate")
        c.create_rectangle(px1, py1, px2, py2, outline=LINE, width=1, tags="plate")

        seg_w = pw / len(SPECTRUM)
        for i, color in enumerate(SPECTRUM):
            c.create_rectangle(px1 + round(i * seg_w), py2 - 2,
                               px1 + round((i + 1) * seg_w), py2,
                               fill=color, outline="", tags="plate")

        cx = (px1 + px2) / 2
        button_h = self.browse_button.winfo_reqheight()
        button_y = py2 - max(14, round(16 * factor)) - button_h / 2
        title_y = button_y - button_h / 2 - max(16, round(18 * factor))
        cards_y = (py1 + title_y) / 2 - 4 * factor

        cw = max(48, round(60 * factor))
        ch = max(26, round(32 * factor))
        gap = max(14, round(18 * factor))
        # HEIC badge (white, sharp border)
        c.create_rectangle(cx - gap - cw, cards_y - ch / 2, cx - gap, cards_y + ch / 2,
                           fill=PAPER, outline=INK, width=1, tags="plate")
        c.create_text(cx - gap - cw / 2, cards_y, text="HEIC", fill=INK,
                      font=(MONO, max(9, round(10 * factor)), "bold"), tags="plate")
        c.create_text(cx, cards_y, text="→", fill=INK, font=(MONO, max(10, round(12 * factor))), tags="plate")
        # JPG badge (black, crisp paper text)
        c.create_rectangle(cx + gap, cards_y - ch / 2, cx + gap + cw, cards_y + ch / 2,
                           fill=INK, outline=INK, width=1, tags="plate")
        c.create_text(cx + gap + cw / 2, cards_y, text="JPG", fill=PAPER,
                      font=(MONO, max(9, round(10 * factor)), "bold"), tags="plate")

        c.create_text(cx, title_y, text="Drop images or videos here", fill=INK,
                      font=("Georgia", max(13, round(16 * factor))), tags="plate")
        c.create_window(cx, button_y, window=self.browse_button, tags="plate")
        self._draw_hero_trail()

    def _draw_hero_trail(self):
        if self.closing:
            return
        c = self.hero
        try:
            c.delete("trail")
        except tk.TclError:
            return
        now = time.monotonic()
        self._hero_cells = {k: v for k, v in self._hero_cells.items() if v[1] > now}
        cw = max(14, round(28 * self.scale))
        ch = max(7, round(14 * self.scale))
        for (col, row), (color, _) in self._hero_cells.items():
            x0, y0 = col * cw + 1, row * ch + 1
            c.create_rectangle(x0, y0, x0 + cw - 1, y0 + ch - 1, fill=color, outline="", tags="trail")
        if self._hero_cells and c.find_withtag("plate"):
            c.tag_lower("trail", "plate")

    def _on_hero_motion(self, event):
        cw = max(14, round(28 * self.scale))
        ch = max(7, round(14 * self.scale))
        col, row = event.x // cw, event.y // ch
        bucket = (col >> 1, row >> 1)
        if bucket == self._hero_bucket:
            return
        self._hero_bucket = bucket
        now = time.monotonic()
        for dc, dr in ((0, 0), (random.choice((-1, 1)), 0), (0, random.choice((-1, 1)))):
            key = (max(0, col + dc), max(0, row + dr))
            if len(self._hero_cells) >= 16 and key not in self._hero_cells:
                self._hero_cells.pop(next(iter(self._hero_cells)))
            self._hero_cells[key] = (random.choice(BRICK_TINTS), now + random.uniform(0.45, 0.85))
        self._draw_hero_trail()
        if self._hero_after is None:
            self._hero_after = self.root.after(60, self._tick_hero)

    def _on_hero_leave(self, _event):
        self._hero_bucket = None

    def _tick_hero(self):
        self._hero_after = None
        if self.closing:
            return
        self._draw_hero_trail()
        if self._hero_cells:
            self._hero_after = self.root.after(60, self._tick_hero)

    def mode(self, motion):
        self.motion = motion
        for i, tab in enumerate(self.tabs):
            active = bool(i) == motion
            tab.configure(bg=INK if active else SUBTLE, fg=PAPER if active else MUTED,
                          highlightbackground=INK if active else LINE)
        options = VIDEOS if motion else IMAGES
        self.fmt.configure(values=options)
        self.fmt.set(options[0])
        self.presets()

    def presets(self):
        fmt = self.fmt.get()
        adjustable = fmt != "GIF" if self.motion else fmt in LOSSY
        options = ["Balanced", "High quality", "Smaller file"] if adjustable else ["Standard"]
        if self.motion and fmt != "GIF":
            options.append("Copy streams")
        self.preset.configure(values=options, state="readonly" if adjustable else "disabled")
        if self.preset.get() not in options:
            self.preset.set(options[0])
        self.hint()

    def hint(self):
        if not self.motion:
            msg = "Videos and animations use the first frame."
        elif self.preset.get() == "Copy streams":
            msg = "Copies compatible tracks at their original quality."
        elif self.fmt.get() == "GIF":
            msg = "Looping animation · 12 fps · up to 720 px wide."
        else:
            msg = "Still images become five-second clips."
        self.note.configure(text=msg)

    def browse(self):
        if self.cancel is not None:
            return
        patterns = " ".join("*." + f.lower() for f in sorted(IMAGE_INPUTS | VIDEO_INPUTS))
        paths = filedialog.askopenfilenames(parent=self.root, title="Add images or videos",
                                            filetypes=[("Images and videos", patterns), ("All files", "*.*")])
        if paths:
            self.add(paths)

    def add(self, paths):
        if self.cancel is not None:
            return
        skipped = 0
        for value in paths:
            path = Path(value).resolve()
            if not path.is_file() or extension(path) not in IMAGE_INPUTS | VIDEO_INPUTS:
                skipped += 1
                continue
            key = str(path).casefold()
            if key in self.jobs:
                continue
            self.jobs[key] = {"path": path, "out": None, "error": None}
            self.tree.insert("", "end", iid=key, values=(extension(path), path.name, "Ready"))
        self.refresh()
        self.status.configure(text=f"{len(self.jobs)} in queue" + (f"  ·  {skipped} unsupported or missing" if skipped else ""))

    def refresh(self):
        self.count.configure(text=f"FILE QUEUE  ·  {len(self.jobs)}")
        self.action.configure(state="normal" if self.jobs else "disabled")
        self.clear.configure(state="normal" if self.jobs and self.cancel is None else "disabled")
        if self.jobs:
            self.empty.place_forget()
        else:
            self.empty.place(relx=.5, rely=.5, anchor="center")

    def remove(self, keys):
        if self.cancel is not None:
            return
        for key in list(keys):
            self.tree.delete(key)
            del self.jobs[key]
        self.refresh()
        self.status.configure(text="Ready")

    def clear_queue(self):
        self.remove(self.jobs.keys())

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose an output folder", initialdir=self.directory)
        if folder:
            self.set_folder(Path(folder))

    def set_folder(self, value):
        self.directory = value
        self.folder_name.configure(text=(value.name or str(value)) if value else "Next to original")
        if value:
            self.reset.pack(before=self.note, anchor="w", pady=(4, 0))
        else:
            self.reset.pack_forget()

    def inspect_row(self, event):
        key = self.tree.identify_row(event.y) if event.type == tk.EventType.ButtonPress else self.tree.focus()
        if key in self.jobs:
            job = self.jobs[key]
            if job["error"]:
                messagebox.showerror(job["path"].name, job["error"], parent=self.root)
            elif job["out"]:
                self.show_output(job["out"])

    def show_output(self, path=None):
        path = path or self.last
        if path and path.is_file():
            subprocess.Popen(f'explorer.exe /select,"{path}"')
        else:
            self.status.configure(text="This output has been moved or deleted.")

    def start(self):
        if self.cancel is not None:
            self.cancel.set()
            self.status.configure(text="Cancelling…")
            return
        if not self.jobs:
            return
        fmt, preset, motion, folder = self.fmt.get(), self.preset.get(), self.motion, self.directory
        self.cancel = stop = threading.Event()
        for widget in [self.browse_button, self.clear, self.change, self.reset, self.fmt, self.preset, *self.tabs]:
            widget.configure(state="disabled")
        self.action.configure(text="CANCEL CONVERSION")
        self.dot.configure(fg=SPECTRUM[0])
        self.reveal.pack_forget()
        self.last = None
        self.finished = self.failed = self.cancelled = 0
        self.started = time.monotonic()
        self.status.configure(text=f"Converting {len(self.jobs)} file(s)…")
        for key, job in self.jobs.items():
            job.update(out=None, error=None)
            self.tree.set(key, "status", "Waiting")

        def worker(item):
            key, job = item
            try:
                if stop.is_set():
                    raise Cancelled()
                self.events.put((key, "Converting", None))
                output = convert(job["path"], folder or job["path"].parent, fmt, motion, preset, stop,
                                 lambda p: self.events.put((key, f"{p}%", None)))
                self.events.put((key, "Saved", output))
            except Cancelled:
                self.events.put((key, "Cancelled", None))
            except Exception as exc:
                self.events.put((key, "Failed", str(exc)))

        def batch():
            workers = min(3, max(1, (os.cpu_count() or 2)//2)) if not motion and all(extension(j["path"]) in IMAGE_INPUTS for j in self.jobs.values()) else 1
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(worker, self.jobs.items()))
            self.events.put((None, "Done", None))
        threading.Thread(target=batch, daemon=True).start()
        self.root.after(50, self.poll)

    def poll(self):
        while not self.events.empty():
            key, status, data = self.events.get_nowait()
            if key is None:
                elapsed = time.monotonic() - self.started
                msg = f"{self.finished} saved in {elapsed:.1f} s"
                if self.failed:
                    msg += f"  ·  {self.failed} failed. Double-click a failed file for details."
                if self.cancelled:
                    msg += f"  ·  {self.cancelled} cancelled"
                self.status.configure(text=msg)
                self.dot.configure(fg=INK if not self.failed else SPECTRUM[0])
                self.cancel = None
                for widget in [self.browse_button, self.clear, self.change, self.reset, *self.tabs]:
                    widget.configure(state="normal")
                self.fmt.configure(state="readonly")
                self.presets()
                self.action.configure(text="CONVERT FILES  →")
                if self.last:
                    self.reveal.pack(side="right")
                if self.closing:
                    self.root.destroy()
                return
            self.tree.set(key, "status", status)
            if status == "Saved":
                self.jobs[key]["out"] = self.last = data
                self.finished += 1
                self.status.configure(text=f"{self.finished} of {len(self.jobs)} saved")
            elif status == "Failed":
                self.jobs[key]["error"] = data
                self.failed += 1
            elif status == "Cancelled":
                self.cancelled += 1
        self.root.after(75, self.poll)

    def close(self):
        if self.cancel is None:
            self.closing = True
            self.root.destroy()
        else:
            self.closing = True
            self.cancel.set()
            self.status.configure(text="Finishing cancellation…")


if __name__ == "__main__":
    import sys
    ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    desk = Desk(root)
    if sys.argv[1:]:
        desk.add(sys.argv[1:])
    root.mainloop()
