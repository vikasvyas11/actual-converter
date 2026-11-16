import ctypes
from ctypes import wintypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import math
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from converter import Cancelled, IMAGE_INPUTS, VIDEO_INPUTS, IMAGES, VIDEOS, LOSSY, convert, extension

PAPER, CARD, INK, MUTED = "#f5f5ef", "#fdfdf9", "#20372c", "#55675b"
FOREST, LIME, LINE = "#1d3c32", "#daf69e", "#d5dcd1"
FONT = "Segoe UI"


def label(parent, text, size=10, fg=INK, bg=None, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg or parent["bg"], font=(FONT, size), bd=0, **kw)


def button(parent, text, command, bg="#e9eee5", fg=INK, **kw):
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground="#c8dfa9",
                     activeforeground=INK, disabledforeground="#77857b", relief="flat", overrelief="flat",
                     bd=0, highlightthickness=1, highlightbackground=bg, highlightcolor="#659758",
                     cursor="hand2", font=(FONT, 10, "bold"), padx=12, pady=5, **kw)


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
        self.jobs = {}
        self.events = queue.Queue()
        self.cancel = None
        self.closing = False
        self.directory = None
        self.last = None
        self.motion = False
        root.title("actual converter")
        root.iconbitmap(str(Path(__file__).with_name("actual.ico")))
        root.configure(bg=PAPER)
        width = min(px(990), root.winfo_screenwidth()-40)
        height = min(px(680), root.winfo_screenheight()-90)
        x = max(0, (root.winfo_screenwidth()-width)//2)
        y = max(0, (root.winfo_screenheight()-height-60)//2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(px(750), px(610))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
                        borderwidth=0, rowheight=px(32), font=(FONT, 10))
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.map("Treeview", background=[("selected", "#dbeacf")], foreground=[("selected", INK)])
        style.configure("TCombobox", padding=5, fieldbackground=CARD, bordercolor=LINE, arrowsize=14)
        style.map("TCombobox", fieldbackground=[("readonly", "#f4f6ef")])

        header = tk.Frame(root, bg=CARD, padx=24, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        mark = tk.Canvas(header, bg=LIME, width=32, height=32, highlightthickness=0)
        mark.pack(side="left")
        mark.create_line(6, 12, 24, 12, 19, 7, fill=FOREST, width=2)
        mark.create_line(26, 20, 8, 20, 13, 25, fill=FOREST, width=2)
        tk.Label(header, text="actual converter", bg=CARD, fg=INK, font=(FONT, 16, "bold")).pack(side="left", padx=10)
        tk.Label(header, text="WINDOWS  /  v1.0", bg=CARD, fg=MUTED, font=("Consolas", 9)).pack(side="right")
        body = tk.Frame(root, bg=PAPER, padx=24, pady=12)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        tk.Label(body, text="Conversion desk", font=("Georgia", 27), bg=PAPER, fg=INK).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        left = tk.Frame(body, bg=PAPER)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=2)
        self.hero = tk.Canvas(left, bg=FOREST, height=160, width=280, highlightthickness=0, cursor="hand2")
        self.hero.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.hero.bind("<Configure>", self.draw_hero)
        self.hero.bind("<Button-1>", lambda e: self.browse())
        self.browse_button = button(self.hero, "＋  Choose files", self.browse, bg=LIME)

        box = tk.Frame(left, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=13, pady=9)
        box.grid(row=1, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        qhead = tk.Frame(box, bg=CARD)
        qhead.grid(sticky="ew")
        self.count = label(qhead, "File queue  ·  0", 12)
        self.count.pack(side="left")
        self.clear = button(qhead, "Clear", self.clear_queue)
        self.clear.pack(side="right")
        rows = tk.Frame(box, bg=CARD)
        rows.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.tree = ttk.Treeview(rows, columns=("type", "name", "status"), show="tree", height=2, selectmode="extended")
        self.tree.column("#0", width=0, stretch=False)
        for name, width in (("type", 50), ("name", 90), ("status", 90)):
            self.tree.column(name, width=width, minwidth=25, stretch=name == "name")
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

        settings = tk.Frame(body, bg=CARD, width=px(280), highlightbackground=LINE, highlightthickness=1)
        settings.grid(row=1, column=1, sticky="nsew")
        settings.grid_propagate(False)
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(0, weight=1)
        fields = tk.Frame(settings, bg=CARD, padx=16, pady=13)
        fields.grid(sticky="nsew")
        tk.Label(fields, text="Output settings", bg=CARD, fg=INK, font=("Georgia", 16)).pack(anchor="w", pady=(0, 10))
        modes = tk.Frame(fields, bg=LINE, padx=2, pady=2)
        modes.pack(fill="x")
        self.tabs = []
        for val, name in enumerate(("Image", "Video")):
            tab = button(modes, name, lambda v=val: self.mode(bool(v)))
            tab.pack(side="left", fill="x", expand=True)
            self.tabs.append(tab)
        self.fmt = self.combo(fields, "Format")
        self.preset = self.combo(fields, "Preset")
        self.fmt.bind("<<ComboboxSelected>>", lambda e: self.presets())
        self.preset.bind("<<ComboboxSelected>>", lambda e: self.hint())
        label(fields, "Save to", 10).pack(anchor="w", pady=(9, 3))
        dest = tk.Frame(fields, bg=CARD)
        dest.pack(fill="x")
        self.change = button(dest, "Change", self.choose_folder)
        self.change.pack(side="right")
        self.folder_name = label(dest, "Next to original", fg=MUTED, anchor="w")
        self.folder_name.pack(side="left", fill="x", expand=True)
        self.reset = button(fields, "Use original folder", lambda: self.set_folder(None))
        self.note = label(fields, "", 9, fg=MUTED, justify="left", wraplength=px(232))
        self.note.pack(anchor="w", pady=(9, 0))
        self.action = button(settings, "Convert files  →", self.start, bg=FOREST, fg="white")
        self.action.grid(row=1, column=0, sticky="ew", padx=16, pady=(3, 14), ipady=3)

        footer = tk.Frame(root, bg="#e9eee5", padx=24, pady=5)
        footer.grid(row=2, column=0, sticky="ew")
        label(footer, "●", 9, fg="#4a8155").pack(side="left")
        self.status = label(footer, "Ready", 9, anchor="w")
        self.status.pack(side="left", padx=6, fill="x", expand=True)
        self.reveal = button(footer, "Show output", self.show_output)
        self.mode(False)
        self.refresh()
        root.bind("<Control-o>", lambda e: self.browse())
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.update_idletasks()
        accept_drops(root, self.add)

    @staticmethod
    def combo(parent, title):
        label(parent, title).pack(anchor="w", pady=(9, 3))
        combo = ttk.Combobox(parent, state="readonly", font=(FONT, 11), width=16)
        combo.pack(fill="x")
        return combo

    def draw_hero(self, event):
        c = self.hero
        c.delete("all")
        w, h = event.width, event.height
        factor = self.scale
        button_height = self.browse_button.winfo_reqheight()
        button_y = h - 15*factor - button_height/2
        title_y = button_y - button_height/2 - 21*factor
        cx, cy = w / 2, title_y/2 - 6*factor
        scale = max(.25, min(1.15*factor, (title_y-25*factor)/90))
        for x in range(14, w, 16):
            for y in range(14, h, 16):
                c.create_oval(x, y, x+1, y+1, outline="", fill="#345247")

        def card(dx, dy, angle, fill, ink, text):
            a = math.radians(angle)
            def pt(x, y):
                return (cx + (dx + x*math.cos(a) - y*math.sin(a))*scale,
                        cy + (dy + x*math.sin(a) + y*math.cos(a))*scale)
            def polygon(points, color):
                c.create_polygon(*[v for p in points for v in pt(*p)], fill=color, outline="")
            polygon([(-44,-30),(34,-30),(44,-20),(44,32),(-44,32)], fill)
            polygon([(33,-30),(44,-20),(33,-20)], ink)
            polygon([(-32,21),(-13,0),(0,13),(10,5),(29,24),(-32,24)], ink)
            c.create_text(*pt(-18,-15), text=text, font=("Consolas", -max(8, int(14*scale)), "bold"), angle=-angle, fill=FOREST)
        card(-42, 3, -13, "#bfd2c4", "#779881", "HEIC")
        card(43, 0, 10, LIME, "#8aa761", "JPG")
        r = 14*scale
        c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=FOREST, outline="#e7f3df", width=1)
        c.create_text(cx, cy, text="→", fill="white", font=(FONT, -max(10, int(18*scale))))
        c.create_text(cx, title_y, text="Drop images or videos here", fill="#f6f8ee", font=("Georgia", 16))
        c.create_window(cx, button_y, window=self.browse_button)

    def mode(self, motion):
        self.motion = motion
        for i, tab in enumerate(self.tabs):
            tab.configure(bg=CARD if bool(i) == motion else "#e4ebe1")
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
        self.count.configure(text=f"File queue  ·  {len(self.jobs)}")
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
            self.reset.pack(before=self.note, anchor="w", pady=(3, 0))
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
        self.action.configure(text="Cancel conversion")
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
                self.cancel = None
                for widget in [self.browse_button, self.clear, self.change, self.reset, *self.tabs]:
                    widget.configure(state="normal")
                self.fmt.configure(state="readonly")
                self.presets()
                self.action.configure(text="Convert files  →")
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
