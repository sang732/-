"""
PDF 도면 PRO — v4.8 (Help System Integrated)
1. [추가] ❓ 도움말 버튼: 프로그램의 모든 기능과 단축키를 상세히 설명하는 팝업 추가.
2. [복구] 벨테스트(🔔): 노란색 원형 마킹 및 회로 연결 시 비프음 발생 로직 유지.
3. [복구] 마킹 자동 삭제: 직선 연결 시 해당 지점의 마킹(tick)이 사라지는 기능 유지.
4. [신규] 우측 클릭 최적화: 그리던 선만 취소하고 '직선 모드'는 계속 유지.
"""
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import fitz 
import math
import winsound
import os
import json
from PIL import Image, ImageTk

CONFIG_FILE = "pdf_config_v4.json"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF 도면 PRO v4.8 — 암호화폐 이자농사꾼 & 후루꾸 전기 ")
        self.geometry("1400x900")
        self.configure(bg="#1e1e2e")

        self.settings = {"default_path": "", "line_width": 5, "font_size": 20, "auto_fit": True, "bell_sound": True}
        self._load_settings()

        self.mode = "pan"
        self.zoom = 1.0
        self.offset_x, self.offset_y = 0.0, 0.0
        self.pdf = None
        self.file_path = ""
        self.is_pdf = True
        self.page_index = 0
        self.page_count = 0
        self.base_img = None
        self.tk_img = None
        self.page_data = {} 
        self.undo_stack = [] 

        self._pan_last = None
        self._line_pts = [] 
        self._bell_start_pt = None
        self._typing = False
        self._t_buf = ""
        self._text_rx, self._text_ry = 0.0, 0.0
        self.color = "#8B4513" 

        self._build_ui()
        self._bind_events()

        if self.settings["default_path"] and os.path.exists(self.settings["default_path"]):
            self.after(200, lambda: self.load_file(self.settings["default_path"]))

    def _load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except: pass

    def _save_settings(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except: pass

    def _build_ui(self):
        bar1 = tk.Frame(self, bg="#13131f", pady=4); bar1.pack(fill=tk.X)
        bar2 = tk.Frame(self, bg="#1a1a2e", pady=3); bar2.pack(fill=tk.X)
        B = dict(bg="#2a2a3e", fg="#e0e0f0", relief=tk.FLAT, padx=10, pady=4, cursor="hand2", font=("Segoe UI", 9, "bold"))
        
        # 상단 메뉴
        tk.Button(bar1, text="📂 열기", command=self.open_file_dialog, **B).pack(side=tk.LEFT, padx=(10, 2))
        tk.Button(bar1, text="💾 저장", command=self.save_work, bg="#2e4a2e", fg="#fff", relief=tk.FLAT, padx=10, pady=4).pack(side=tk.LEFT, padx=2)
        tk.Button(bar1, text="⚙️ 설정", command=self.open_settings, **B).pack(side=tk.LEFT, padx=2)
        tk.Button(bar1, text="❓ 도움말", command=self.show_help, bg="#4a4a6a", fg="#fff", relief=tk.FLAT, padx=10, pady=4).pack(side=tk.LEFT, padx=2)
        
        tk.Frame(bar1, bg="#33334d", width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        tk.Button(bar1, text="◀", command=self.prev_page, **B).pack(side=tk.LEFT)
        self._page_lbl = tk.Label(bar1, text="0 / 0", bg="#13131f", fg="#00ffcc", font=("Consolas", 10, "bold"), width=10)
        self._page_lbl.pack(side=tk.LEFT)
        tk.Button(bar1, text="▶", command=self.next_page, **B).pack(side=tk.LEFT)

        self._btn = {}
        for key, label in [("pan", "🖐 이동"), ("line", "📏 직선"), ("text", "🔤 텍스트"), ("mark", "✔️ 마킹"), ("bell", "🔔 벨테스트")]:
            style = B.copy()
            if key == "bell": style.update({"bg": "#4e342e", "fg": "#ffcc00"})
            b = tk.Button(bar1, text=label, command=lambda k=key: self.set_mode(k), **style)
            b.pack(side=tk.LEFT, padx=2); self._btn[key] = b

        tk.Button(bar1, text="🧹 초기화", command=self.reset_work, bg="#5c2d2d", fg="#ffcccc", relief=tk.FLAT, padx=10).pack(side=tk.RIGHT, padx=10)

        # 하단 메뉴 (Undo, 색상, 굵기)
        tk.Button(bar2, text="⟲ Undo", command=self.undo, **B).pack(side=tk.LEFT, padx=(10,2))
        color_list = [("갈(L1)", "#8B4513"), ("흑(L2)", "#000000"), ("회(L3)", "#808080"), ("청(N)", "#0000FF"), ("빨(P)", "#FF0000")]
        for name, code in color_list:
            tk.Button(bar2, text=name, bg=code, fg="white", font=("맑은 고딕", 8, "bold"), width=7,
                      command=lambda c=code: self.set_color(c)).pack(side=tk.LEFT, padx=2)

        self._color_preview = tk.Label(bar2, text="🎨 기타", bg=self.color, fg="#ffffff", font=("맑은 고딕", 9, "bold"), padx=10, cursor="hand2", relief=tk.RAISED)
        self._color_preview.pack(side=tk.LEFT, padx=10)
        self._color_preview.bind("<Button-1>", lambda e: self._choose_color())

        tk.Label(bar2, text="✏ 굵기:", bg="#1a1a2e", fg="#888").pack(side=tk.LEFT, padx=(10,2))
        self._width_var = tk.IntVar(value=self.settings["line_width"])
        self._width_lbl = tk.Label(bar2, text=f"{self.settings['line_width']}px", bg="#1a1a2e", fg="#ffcc00", width=4)
        self._width_lbl.pack(side=tk.LEFT)
        tk.Scale(bar2, from_=1, to=20, orient=tk.HORIZONTAL, variable=self._width_var, command=self._on_width_change, length=80, showvalue=False, bg="#1a1a2e", highlightthickness=0).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self, bg="#1e1e2e", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    # [신규] 도움말 팝업 함수
    def show_help(self):
        help_win = tk.Toplevel(self)
        help_win.title("PDF 도면 PRO 사용 도움말")
        help_win.geometry("600x650")
        help_win.configure(bg="#1a1a2e")
        
        txt = tk.Text(help_win, bg="#1a1a2e", fg="#e0e0f0", font=("맑은 고딕", 10), padx=20, pady=20, relief=tk.FLAT)
        txt.pack(fill=tk.BOTH, expand=True)
        
        guide = """
[ PDF 도면 PRO v4.8 — 사용 설명서 ]

1. 기본 도구 설명
   - 🖐 이동: 도면을 클릭 드래그하여 이동합니다. (마우스 휠로 확대/축소)
   - 📏 직선: 도면에 전기 결선을 그립니다. 
     * 마우스 왼쪽 클릭: 시작점 지정 및 연속 그리기
     * 마우스 오른쪽 클릭: 현재 그리던 선만 종료 (모드는 유지됨)
     * 수평/수직 보정: 자동으로 직선을 맞춰줍니다.
   - 🔤 텍스트: 클릭 후 타이핑하여 글자를 넣습니다. (Enter로 확정)
   - ✔️ 마킹: 단축 체크 표시를 남깁니다. (직선 연결 시 자동 삭제됨)
   - 🔔 벨테스트: 회로의 연결 상태를 확인합니다.
     * 시작점과 끝점을 클릭하면 연결 시 '삐-' 소리가 납니다.
     * 벨테스트 중에는 노란색 원형 마킹이 표시됩니다.

2. 색상 및 스타일
   - 하단 버튼(갈, 흑, 회, 청, 빨)으로 전기 기능사 규격 색상을 즉시 선택합니다.
   - 색상을 바꿔도 이전에 그린 선의 색상은 변하지 않습니다.
   - ✏ 굵기 슬라이더로 선과 마킹의 두께를 조절합니다.

3. 주요 편의 기능
   - ⚙️ 설정: 기본 선 굵기, 글자 크기, 파일 오픈 시 자동 화면 맞춤을 설정합니다.
   - ⟲ Undo: 마지막 작업을 취소합니다. (단축키: Ctrl + Z)
   - 🧹 초기화: 현재 페이지의 모든 작업 내용을 지웁니다.
   - 💾 저장: 작업 내용이 포함된 새로운 PDF로 저장합니다.

4. 팁 
   - 직선을 그리다가 색상을 바꿔야 할 땐, 그냥 하단 색상 버튼을 누르세요.
   - 선을 다 그렸으면 우측 클릭 한 번으로 깔끔하게 끊고 다음 선을 그리세요.
        """
        txt.insert(tk.END, guide)
        txt.config(state=tk.DISABLED)
        tk.Button(help_win, text="닫기", command=help_win.destroy, bg="#2a2a3e", fg="#fff", padx=30).pack(pady=10)

    def set_color(self, c):
        self.color = c
        self._color_preview.config(bg=c)
        self.canvas.focus_set()
        self.draw()

    def set_mode(self, m):
        self.mode = m; self._line_pts = []; self._bell_start_pt = None
        for k, b in self._btn.items(): 
            b.config(bg="#5a2a7e" if k==m else ("#4e342e" if k=="bell" else "#2a2a3e"))

    def _on_right_click(self, e):
        self._line_pts = []; self._bell_start_pt = None
        self.draw()

    def _on_click(self, e):
        if not self.base_img: return
        rx, ry = self._to_ratio(e.x, e.y)
        
        if self.mode == "line":
            if self._line_pts:
                p1 = self._line_pts[-1]
                dx, dy = abs(rx-p1[0]), abs(ry-p1[1])
                snap_pt = (rx, p1[1]) if dx > dy else (p1[0], ry)
                edge = {"a": p1, "b": snap_pt, "color": self.color, "width": self.settings["line_width"]}
                self.page_data[self.page_index]["edges"].append(edge)
                self.undo_stack.append({"page": self.page_index, "type": "edge"})
                
                # [복구] 마킹 자동 삭제
                ticks = self.page_data[self.page_index]["ticks"]
                self.page_data[self.page_index]["ticks"] = [t for t in ticks if math.dist((t["rx"], t["ry"]), snap_pt) > 0.02]
                self._line_pts.append(snap_pt)
            else:
                self._line_pts.append((rx, ry))
            self.draw()
            
        elif self.mode == "mark":
            mark = {"rx": rx, "ry": ry, "color": self.color, "width": self.settings["line_width"]}
            self.page_data[self.page_index]["ticks"].append(mark)
            self.undo_stack.append({"page": self.page_index, "type": "tick"}); self.draw()
            
        elif self.mode == "bell":
            if self._bell_start_pt is None:
                self._bell_start_pt = (rx, ry)
            else:
                if self._check_bell_connection(self._bell_start_pt, (rx, ry)):
                    if self.settings["bell_sound"]: winsound.Beep(1000, 400)
                self._bell_start_pt = None
            self.draw()

        elif self.mode == "text":
            self._commit_text(); self._text_rx, self._text_ry = rx, ry; self._typing, self._t_buf = True, ""; self.canvas.focus_set(); self._update_text_view()
        elif self.mode == "pan": self._pan_last = (e.x, e.y)

    def draw(self):
        if not self.base_img: return
        self.canvas.delete("all")
        dw, dh = int(self.base_img.width*self.zoom), int(self.base_img.height*self.zoom)
        self.tk_img = ImageTk.PhotoImage(self.base_img.resize((dw, dh), Image.LANCZOS))
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_img)
        
        d = self.page_data[self.page_index]
        for e in d["edges"]:
            x1, y1 = self._to_canvas(*e["a"]); x2, y2 = self._to_canvas(*e["b"])
            self.canvas.create_line(x1, y1, x2, y2, fill=e["color"], width=max(1, int(e["width"]*self.zoom)))
        
        for m in d["ticks"]:
            cx, cy = self._to_canvas(m["rx"], m["ry"]); sz = 12*self.zoom
            self.canvas.create_line(cx-sz*0.8, cy+sz*0.2, cx, cy+sz, fill=m["color"], width=max(1, int(m["width"]*self.zoom)))
            self.canvas.create_line(cx, cy+sz, cx+sz*1.2, cy-sz*0.8, fill=m["color"], width=max(1, int(m["width"]*self.zoom)))
        
        if self._bell_start_pt:
            bx, by = self._to_canvas(*self._bell_start_pt); r = 8*self.zoom
            self.canvas.create_oval(bx-r, by-r, bx+r, by+r, outline="#ffff00", width=2)

        for t in d["texts"]:
            x, y = self._to_canvas(t["rx"], t["ry"])
            self.canvas.create_text(x, y, text=t["text"], fill=t["color"], anchor=tk.NW, font=("Arial", max(4, int(t["font_size"]*self.zoom))))

    # --- 유틸리티 및 시스템 함수 (보존) ---
    def _check_bell_connection(self, p1, p2):
        edges = self.page_data[self.page_index]["edges"]
        q = [p1]; visited = set()
        while q:
            curr = q.pop(0)
            if math.dist(curr, p2) < 0.02: return True
            for i, e in enumerate(edges):
                if i not in visited:
                    if math.dist(curr, e["a"]) < 0.02: visited.add(i); q.append(e["b"])
                    elif math.dist(curr, e["b"]) < 0.02: visited.add(i); q.append(e["a"])
        return False

    def open_settings(self):
        win = tk.Toplevel(self); win.title("환경 설정"); win.geometry("400x300"); win.configure(bg="#2a2a3e")
        def save():
            self.settings["line_width"] = int(w_ent.get()); self.settings["font_size"] = int(f_ent.get())
            self.settings["auto_fit"] = fit_var.get(); self._save_settings(); win.destroy(); self.draw()
        tk.Label(win, text="[ 시스템 설정 ]", bg="#2a2a3e", fg="#00ffcc", font=("Segoe UI", 12, "bold")).pack(pady=10)
        f1, f2 = tk.Frame(win, bg="#2a2a3e"), tk.Frame(win, bg="#2a2a3e")
        f1.pack(pady=5); f2.pack(pady=5)
        tk.Label(f1, text="기본 선 굵기:", bg="#2a2a3e", fg="#fff").pack(side=tk.LEFT)
        w_ent = tk.Entry(f1, width=5); w_ent.insert(0, str(self.settings["line_width"])); w_ent.pack(side=tk.LEFT, padx=5)
        tk.Label(f2, text="기본 글자 크기:", bg="#2a2a3e", fg="#fff").pack(side=tk.LEFT)
        f_ent = tk.Entry(f2, width=5); f_ent.insert(0, str(self.settings["font_size"])); f_ent.pack(side=tk.LEFT, padx=5)
        fit_var = tk.BooleanVar(value=self.settings["auto_fit"])
        tk.Checkbutton(win, text="도면 열기 시 화면 자동 맞춤", variable=fit_var, bg="#2a2a3e", fg="#fff", selectcolor="#1a1a2e").pack(pady=10)
        tk.Button(win, text="저장 및 적용", command=save, bg="#4e342e", fg="#fff", padx=20).pack(pady=20)

    def undo(self):
        if self.undo_stack:
            item = self.undo_stack.pop(); self.page_data[item["page"]][item["type"]+"s"].pop(); self.draw()
    def _on_move(self, e):
        if self.mode == "pan" and self._pan_last:
            self.offset_x += e.x - self._pan_last[0]; self.offset_y += e.y - self._pan_last[1]; self._pan_last = (e.x, e.y); self.draw()
        elif self.mode == "line" and self._line_pts:
            self.draw(); p1_c = self._to_canvas(*self._line_pts[-1])
            self.canvas.create_line(p1_c[0], p1_c[1], e.x, e.y, fill=self.color, dash=(4,4))
    def save_work(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path: return
        try:
            out_pdf = fitz.open(self.file_path) if self.is_pdf else fitz.open()
            if not self.is_pdf:
                page = out_pdf.new_page(width=self.base_img.width, height=self.base_img.height)
                page.insert_image(page.rect, filename=self.file_path)
            for i in range(self.page_count):
                page = out_pdf[i]; pw, ph = page.rect.width, page.rect.height; d = self.page_data[i]
                for e in d["edges"]:
                    rgb = [int(e["color"][j:j+2], 16)/255 for j in (1,3,5)]
                    page.draw_line(fitz.Point(e["a"][0]*pw, e["a"][1]*ph), fitz.Point(e["b"][0]*pw, e["b"][1]*ph), color=rgb, width=e["width"])
                for m in d["ticks"]:
                    rgb = [int(m["color"][j:j+2], 16)/255 for j in (1,3,5)]
                    cx, cy = m["rx"]*pw, m["ry"]*ph
                    page.draw_line(fitz.Point(cx-8, cy+2), fitz.Point(cx, cy+10), color=rgb, width=2)
                    page.draw_line(fitz.Point(cx, cy+10), fitz.Point(cx+12, cy-8), color=rgb, width=2)
                for t in d["texts"]:
                    rgb = [int(t["color"][j:j+2], 16)/255 for j in (1,3,5)]
                    page.insert_text((t["rx"]*pw, t["ry"]*ph + t["font_size"]), t["text"], fontsize=t["font_size"], color=rgb)
            out_pdf.save(path); out_pdf.close(); messagebox.showinfo("성공", "저장 완료!")
        except Exception as e: messagebox.showerror("오류", str(e))
    def _to_ratio(self, cx, cy): return (cx-self.offset_x)/(self.base_img.width*self.zoom), (cy-self.offset_y)/(self.base_img.height*self.zoom)
    def _to_canvas(self, rx, ry): return rx*self.base_img.width*self.zoom+self.offset_x, ry*self.base_img.height*self.zoom+self.offset_y
    def _on_width_change(self, v): self.settings["line_width"]=int(v); self._width_lbl.config(text=f"{v}px")
    def _on_wheel(self, e): f=1.1 if e.delta>0 else 0.9; self.zoom*=f; self.draw()
    def _bind_events(self):
        self.canvas.bind("<Button-1>", self._on_click); self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Motion>", self._on_move); self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Key>", lambda e: self._on_key(e)); self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Escape>", lambda e: self.set_mode(None)); self.bind("<Configure>", lambda e: self.after(50, self.fit_to_window))
    def _on_key(self, e):
        if not self._typing: return
        if e.keysym == "Return": self._commit_text()
        elif e.keysym == "BackSpace": self._t_buf = self._t_buf[:-1]
        elif len(e.char) == 1: self._t_buf += e.char
        self._update_text_view()
    def _update_text_view(self):
        self.draw()
        if self._typing:
            tx, ty = self._to_canvas(self._text_rx, self._text_ry)
            self.canvas.create_text(tx, ty, text=self._t_buf+"┃", fill=self.color, anchor=tk.NW, font=("Arial", int(self.settings["font_size"]*self.zoom)))
    def _commit_text(self):
        if self._typing and self._t_buf:
            txt = {"text":self._t_buf, "rx":self._text_rx, "ry":self._text_ry, "color":self.color, "font_size":self.settings["font_size"]}
            self.page_data[self.page_index]["texts"].append(txt); self.undo_stack.append({"page":self.page_index, "type":"text"})
        self._typing = False; self.draw()
    def load_file(self, path):
        try:
            self.file_path = path; self.is_pdf = path.lower().endswith(".pdf")
            if self.is_pdf: self.pdf = fitz.open(path); self.page_count = len(self.pdf)
            else: self.pdf = None; self.page_count = 1
            self.page_index = 0; self.page_data = {i: {"texts":[], "edges":[], "ticks":[]} for i in range(self.page_count)}
            self.settings["default_path"] = path; self._save_settings(); self._load_page(); self.after(100, self.fit_to_window)
        except Exception as e: messagebox.showerror("오류", str(e))
    def _load_page(self):
        if self.is_pdf:
            pix = self.pdf[self.page_index].get_pixmap(matrix=fitz.Matrix(2, 2))
            self.base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else: self.base_img = Image.open(self.file_path).convert("RGB")
        self._page_lbl.config(text=f"{self.page_index+1} / {self.page_count}"); self.draw()
    def open_file_dialog(self):
        p = filedialog.askopenfilename(filetypes=[("지원 파일", "*.pdf *.png *.jpg")]); self.load_file(p) if p else None
    def prev_page(self):
        if self.page_index > 0: self.page_index -= 1; self._load_page(); self.fit_to_window()
    def next_page(self):
        if self.page_index < self.page_count-1: self.page_index += 1; self._load_page(); self.fit_to_window()
    def reset_work(self): self.page_data[self.page_index] = {"texts":[], "edges":[], "ticks":[]}; self.draw()
    def _choose_color(self):
        c = colorchooser.askcolor(initialcolor=self.color)[1]; self.set_color(c) if c else None
    def fit_to_window(self):
        if not self.base_img: return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10 or ch < 10: return
        w, h = self.base_img.size
        self.zoom = min(cw/w, ch/h) * 0.95
        self.offset_x, self.offset_y = (cw - w*self.zoom)/2, (ch - h*self.zoom)/2
        self.draw()

if __name__ == "__main__":
    App().mainloop()