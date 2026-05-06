"""
PDF 도면 PRO — v5.5 (Page Rotation Feature)
제작: 이상권 강사님 (수원 동성직업전문학교)

[v5.5 수정사항]
1. 도면(페이지) 회전 기능 추가
   - 툴바 1 우측에 [↺ 좌회전 90°] [↻ 우회전 90°] 버튼 추가
   - 단축키: Ctrl+L (좌회전), Ctrl+R (우회전)
   - 페이지별 회전 각도 독립 관리 (0 / 90 / 180 / 270도)
   - 회전 시 기존 작업(선/마킹/텍스트) 좌표도 자동 변환 유지
   - 회전 상태 표시 레이블 (툴바 우측)
2. 기존 모든 기능 완전 유지
"""

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import fitz
import math
import winsound
import os
import json
import datetime
from PIL import Image, ImageTk

CONFIG_FILE = "pdf_config_v5_pro.json"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF 도면 PRO v5.5 — 이상권 드림 (전기 교육용)")
        self.geometry("1500x950")
        self.configure(bg="#1e1e2e")

        self.settings = {
            "default_path": "",
            "line_width": 5,
            "font_size": 20,
            "auto_fit": True,
            "bell_sound": True,
            "theme_color": "#1e1e2e",
            "last_save_dir": os.path.expanduser("~"),
        }
        self._load_settings()

        self.mode = "pan"
        self.zoom = 1.0
        self.offset_x, self.offset_y = 0.0, 0.0
        self.pdf = None
        self.file_path = ""
        self.is_pdf = True
        self.page_index = 0
        self.page_count = 0
        self.base_img = None        # 회전 적용된 PIL Image
        self._raw_img = None        # 원본(회전 전) PIL Image — 회전 재계산용
        self.tk_img = None
        self.page_data = {}
        self.undo_stack = []

        self._pan_last = None
        self._line_pts = []
        self._bell_start_pt = None

        self._typing = False
        self._t_buf = ""
        self._text_rx, self._text_ry = 0.0, 0.0
        self._cursor_visible = True
        self._cursor_job = None

        self.color = "#8B4513"

        self._build_ui()
        self._bind_events()

        if self.settings["default_path"] and os.path.exists(self.settings["default_path"]):
            self.after(500, lambda: self.load_file(self.settings["default_path"]))

    # ═══════════════════════════════════════════
    # 설정
    # ═══════════════════════════════════════════
    def _load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except:
                pass

    def _save_settings(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except:
            pass

    # ═══════════════════════════════════════════
    # UI 빌드
    # ═══════════════════════════════════════════
    def _build_ui(self):
        # ── 툴바 1 ──────────────────────────────
        bar1 = tk.Frame(self, bg="#13131f", height=50, pady=5)
        bar1.pack(fill=tk.X)

        btn_style = {
            "bg": "#2a2a3e", "fg": "#e0e0f0", "relief": tk.FLAT,
            "padx": 11, "pady": 6, "cursor": "hand2",
            "font": ("맑은 고딕", 9, "bold"), "activebackground": "#3d3d5c",
        }

        tk.Button(bar1, text="📂 도면 열기", command=self.open_file_dialog, **btn_style).pack(side=tk.LEFT, padx=(15, 2))
        tk.Button(bar1, text="💾 작업 저장", command=self.save_work,        bg="#2e4a2e", fg="#ffffff", relief=tk.FLAT, padx=11, pady=6, cursor="hand2", font=("맑은 고딕", 9, "bold")).pack(side=tk.LEFT, padx=2)
        tk.Button(bar1, text="⚙️ 설정",     command=self.open_settings,    **btn_style).pack(side=tk.LEFT, padx=2)
        tk.Button(bar1, text="❓ 도움말",    command=self.show_help,        bg="#4a4a6a", fg="#ffffff", relief=tk.FLAT, padx=11, pady=6, cursor="hand2", font=("맑은 고딕", 9, "bold")).pack(side=tk.LEFT, padx=2)

        tk.Frame(bar1, bg="#33334d", width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        tk.Button(bar1, text="◀", command=self.prev_page, **btn_style).pack(side=tk.LEFT)
        self._page_lbl = tk.Label(bar1, text="0 / 0", bg="#13131f", fg="#00ffcc",
                                  font=("Consolas", 11, "bold"), width=10)
        self._page_lbl.pack(side=tk.LEFT)
        tk.Button(bar1, text="▶", command=self.next_page, **btn_style).pack(side=tk.LEFT)

        tk.Frame(bar1, bg="#33334d", width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self._btn = {}
        tool_list = [
            ("pan",  "🖐 이동"),
            ("line", "📏 직선결선"),
            ("text", "🔤 문자"),
            ("mark", "✔️ 마킹"),
            ("bell", "🔔 벨테스트"),
        ]
        for key, label in tool_list:
            s = btn_style.copy()
            if key == "bell":
                s.update({"bg": "#4e342e", "fg": "#ffcc00"})
            b = tk.Button(bar1, text=label, command=lambda k=key: self.set_mode(k), **s)
            b.pack(side=tk.LEFT, padx=2)
            self._btn[key] = b

        # ── [신규] 회전 버튼 그룹 ─────────────
        tk.Frame(bar1, bg="#33334d", width=2).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        rot_lbl_style = {"bg": "#13131f", "fg": "#aaaacc", "font": ("맑은 고딕", 8)}
        tk.Label(bar1, text="도면 회전", **rot_lbl_style).pack(side=tk.LEFT, padx=(2, 1))

        tk.Button(bar1, text="↺ 좌 90°",
                  command=lambda: self.rotate_page(-90),
                  bg="#1e3a5f", fg="#88ccff", relief=tk.FLAT,
                  padx=10, pady=6, cursor="hand2",
                  font=("맑은 고딕", 9, "bold"),
                  activebackground="#2a4f7a").pack(side=tk.LEFT, padx=2)

        tk.Button(bar1, text="↻ 우 90°",
                  command=lambda: self.rotate_page(90),
                  bg="#1e3a5f", fg="#88ccff", relief=tk.FLAT,
                  padx=10, pady=6, cursor="hand2",
                  font=("맑은 고딕", 9, "bold"),
                  activebackground="#2a4f7a").pack(side=tk.LEFT, padx=2)

        tk.Button(bar1, text="↕ 180°",
                  command=lambda: self.rotate_page(180),
                  bg="#1e3a5f", fg="#88ccff", relief=tk.FLAT,
                  padx=10, pady=6, cursor="hand2",
                  font=("맑은 고딕", 9, "bold"),
                  activebackground="#2a4f7a").pack(side=tk.LEFT, padx=2)

        # 현재 회전 각도 표시
        self._rot_lbl = tk.Label(bar1, text="  0°", bg="#13131f", fg="#ffaa00",
                                 font=("Consolas", 10, "bold"), width=5)
        self._rot_lbl.pack(side=tk.LEFT, padx=(2, 4))

        # 초기화 버튼 (오른쪽 끝)
        tk.Button(bar1, text="🧹 초기화", command=self.reset_work,
                  bg="#5c2d2d", fg="#ffcccc", relief=tk.FLAT, padx=11).pack(side=tk.RIGHT, padx=15)

        # ── 툴바 2 ──────────────────────────────
        bar2 = tk.Frame(self, bg="#1a1a2e", height=45, pady=4)
        bar2.pack(fill=tk.X)

        tk.Button(bar2, text="⟲ 마지막 작업 취소 (Undo)", command=self.undo, **btn_style).pack(side=tk.LEFT, padx=(15, 5))

        color_list = [
            ("갈색(L1)", "#8B4513"), ("흑색(L2)", "#000000"), ("회색(L3)", "#808080"),
            ("청색(N)", "#0000FF"), ("적색(P)", "#FF0000"),
        ]
        for name, code in color_list:
            tk.Button(bar2, text=name, bg=code, fg="white",
                      font=("맑은 고딕", 8, "bold"), width=9,
                      command=lambda c=code: self.set_color(c)).pack(side=tk.LEFT, padx=2)

        self._color_preview = tk.Label(bar2, text="🎨 색상변경", bg=self.color, fg="#ffffff",
                                       font=("맑은 고딕", 9, "bold"), padx=12, relief=tk.RAISED)
        self._color_preview.pack(side=tk.LEFT, padx=10)
        self._color_preview.bind("<Button-1>", lambda e: self._choose_color())

        tk.Label(bar2, text="✏ 선굵기:", bg="#1a1a2e", fg="#bbbbbb").pack(side=tk.LEFT, padx=(8, 2))
        self._width_var = tk.IntVar(value=self.settings["line_width"])
        self._width_lbl = tk.Label(bar2, text=f"{self.settings['line_width']}px",
                                   bg="#1a1a2e", fg="#ffcc00", width=4)
        self._width_lbl.pack(side=tk.LEFT)
        ttk.Scale(bar2, from_=1, to=30, orient=tk.HORIZONTAL,
                  variable=self._width_var, command=self._on_width_change,
                  length=100).pack(side=tk.LEFT, padx=4)

        tk.Label(bar2, text="🔤 글자크기:", bg="#1a1a2e", fg="#bbbbbb").pack(side=tk.LEFT, padx=(12, 2))
        self._font_var = tk.IntVar(value=self.settings["font_size"])
        self._font_lbl = tk.Label(bar2, text=f"{self.settings['font_size']}pt",
                                  bg="#1a1a2e", fg="#00ffcc", width=4)
        self._font_lbl.pack(side=tk.LEFT)
        ttk.Scale(bar2, from_=8, to=72, orient=tk.HORIZONTAL,
                  variable=self._font_var, command=self._on_font_change,
                  length=100).pack(side=tk.LEFT, padx=4)

        self.canvas = tk.Canvas(self, bg="#1e1e2e", highlightthickness=0, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    # ═══════════════════════════════════════════
    # 모드 / 색상 / 굵기 / 글자크기
    # ═══════════════════════════════════════════
    def set_mode(self, m):
        if self._typing:
            self._cancel_text()
        self.mode = m
        self._line_pts = []
        self._bell_start_pt = None
        for k, b in self._btn.items():
            b.config(bg="#5a2a7e" if k == m else ("#4e342e" if k == "bell" else "#2a2a3e"))

    def set_color(self, c):
        self.color = c
        self._color_preview.config(bg=c)

    def _on_width_change(self, v):
        self.settings["line_width"] = int(float(v))
        self._width_lbl.config(text=f"{int(float(v))}px")

    def _on_font_change(self, v):
        self.settings["font_size"] = int(float(v))
        self._font_lbl.config(text=f"{int(float(v))}pt")
        if self._typing:
            self._update_text_view()

    # ═══════════════════════════════════════════
    # [신규] 페이지 회전
    # ═══════════════════════════════════════════
    def rotate_page(self, delta_deg):
        """
        delta_deg: +90(우회전) / -90(좌회전) / 180
        현재 페이지의 rotation을 변경하고,
        기존 작업 데이터(edges, ticks, texts)의 좌표를 회전 변환한다.
        """
        if not self.base_img:
            return
        if self._typing:
            self._commit_text()

        d = self.page_data[self.page_index]
        old_rot = d.get("rotation", 0)
        new_rot = (old_rot + delta_deg) % 360

        # 좌표 변환: (rx, ry) → 회전 후 새 (rx', ry')
        # 회전은 이미지 중심(0.5, 0.5) 기준
        def transform(rx, ry, deg):
            # deg 만큼 시계방향(+) 또는 반시계(-) 회전
            # 정규화 좌표 (0~1) 기준 중심점 (0.5, 0.5)
            cx, cy = rx - 0.5, ry - 0.5
            rad = math.radians(deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            nx = cos_a * cx - sin_a * cy + 0.5
            ny = sin_a * cx + cos_a * cy + 0.5
            return nx, ny

        actual_delta = delta_deg  # 실제 회전할 각도

        # edges 좌표 변환
        for edge in d["edges"]:
            edge["a"] = transform(*edge["a"], actual_delta)
            edge["b"] = transform(*edge["b"], actual_delta)

        # ticks 좌표 변환
        for tick in d["ticks"]:
            tick["rx"], tick["ry"] = transform(tick["rx"], tick["ry"], actual_delta)

        # texts 좌표 변환
        for text in d["texts"]:
            text["rx"], text["ry"] = transform(text["rx"], text["ry"], actual_delta)

        # line_pts (그리던 중인 선) 변환
        self._line_pts = [transform(rx, ry, actual_delta) for rx, ry in self._line_pts]

        # rotation 저장
        d["rotation"] = new_rot

        # 이미지 회전 적용 (PIL: expand=True → 잘림 없음)
        # PIL rotate: 반시계 방향이므로 부호 반전
        self.base_img = self._raw_img.rotate(-new_rot, expand=True)

        # 회전 표시 갱신
        self._rot_lbl.config(text=f"{new_rot:>3}°")

        # fit & redraw
        self.fit_to_window()

    def _current_rotation(self):
        if not self.page_data:
            return 0
        return self.page_data[self.page_index].get("rotation", 0)

    # ═══════════════════════════════════════════
    # 마킹 삭제 헬퍼
    # ═══════════════════════════════════════════
    def _remove_ticks_near(self, *points, threshold=0.04):
        ticks = self.page_data[self.page_index]["ticks"]
        self.page_data[self.page_index]["ticks"] = [
            t for t in ticks
            if all(math.dist((t["rx"], t["ry"]), pt) > threshold for pt in points)
        ]

    # ═══════════════════════════════════════════
    # 클릭 이벤트
    # ═══════════════════════════════════════════
    def _on_click(self, e):
        if not self.base_img:
            return
        rx, ry = self._to_ratio(e.x, e.y)

        if self.mode == "line":
            if self._typing:
                self._cancel_text()
            if self._line_pts:
                p1 = self._line_pts[-1]
                dx, dy = abs(rx - p1[0]), abs(ry - p1[1])
                snap_pt = (rx, p1[1]) if dx > dy else (p1[0], ry)
                self._remove_ticks_near(p1, snap_pt, (rx, ry))
                edge = {"a": p1, "b": snap_pt, "color": self.color, "width": self.settings["line_width"]}
                self.page_data[self.page_index]["edges"].append(edge)
                self.undo_stack.append({"page": self.page_index, "type": "edge"})
                self._line_pts.append(snap_pt)
            else:
                self._remove_ticks_near((rx, ry))
                self._line_pts.append((rx, ry))
            self.draw()

        elif self.mode == "mark":
            if self._typing:
                self._cancel_text()
            self.page_data[self.page_index]["ticks"].append(
                {"rx": rx, "ry": ry, "color": self.color, "width": self.settings["line_width"]}
            )
            self.undo_stack.append({"page": self.page_index, "type": "tick"})
            self.draw()

        elif self.mode == "bell":
            if self._typing:
                self._cancel_text()
            if self._bell_start_pt is None:
                self._bell_start_pt = (rx, ry)
            else:
                if self._check_bell_connection(self._bell_start_pt, (rx, ry)):
                    if self.settings["bell_sound"]:
                        winsound.Beep(1200, 400)
                self._bell_start_pt = None
            self.draw()

        elif self.mode == "text":
            if self._typing:
                self._commit_text()
            self._text_rx, self._text_ry = rx, ry
            self._typing = True
            self._t_buf = ""
            self.canvas.focus_set()
            self._cursor_visible = True
            self._start_cursor_blink()
            self._update_text_view()

        elif self.mode == "pan":
            if self._typing:
                self._commit_text()
            self._pan_last = (e.x, e.y)
            self.canvas.config(cursor="fleur")   # 이동 중 커서

    # ═══════════════════════════════════════════
    # 텍스트 입력
    # ═══════════════════════════════════════════
    def _start_cursor_blink(self):
        if self._cursor_job:
            self.after_cancel(self._cursor_job)
        self._blink_cursor()

    def _blink_cursor(self):
        if not self._typing:
            return
        self._cursor_visible = not self._cursor_visible
        self._update_text_view()
        self._cursor_job = self.after(530, self._blink_cursor)

    def _stop_cursor_blink(self):
        if self._cursor_job:
            self.after_cancel(self._cursor_job)
            self._cursor_job = None

    def _update_text_view(self):
        self.draw()
        if not self._typing:
            return
        x, y = self._to_canvas(self._text_rx, self._text_ry)
        fs = max(8, int(self.settings["font_size"] * self.zoom))
        font = ("맑은 고딕", fs, "bold")
        display_text = self._t_buf + ("|" if self._cursor_visible else " ")
        tid = self.canvas.create_text(x + 4, y + 4, text=display_text,
                                      fill=self.color, anchor=tk.NW, font=font)
        try:
            bb = self.canvas.bbox(tid)
        except Exception:
            bb = None
        PAD = 6
        if bb:
            bx1, by1, bx2, by2 = bb
            bx1 -= PAD; by1 -= PAD; bx2 += PAD; by2 += PAD
        else:
            est_w = max(80, fs * (len(display_text) + 2))
            bx1, by1 = x - PAD, y - PAD
            bx2, by2 = x + est_w, y + fs + 12
        self.canvas.create_rectangle(bx1, by1, bx2, by2,
                                     outline="#00ffcc", width=1, dash=(5, 4))
        self.canvas.create_text(bx1, by2 + 4, text="Enter=확정  Esc=취소",
                                fill="#888899", anchor=tk.NW,
                                font=("맑은 고딕", max(7, fs - 6)))

    def _on_key(self, e):
        # pan 이동 중 Esc → 이동 정지
        if e.keysym == "Escape" and self.mode == "pan" and self._pan_last:
            self._stop_pan()
            return
        if not self._typing:
            return
        if e.keysym == "Return":
            self._commit_text()
        elif e.keysym == "Escape":
            self._cancel_text()
        elif e.keysym == "BackSpace":
            self._t_buf = self._t_buf[:-1]
            self._update_text_view()
        elif e.char and e.char.isprintable():
            self._t_buf += e.char
            self._update_text_view()

    def _stop_pan(self):
        """pan 이동 정지 — 커서 원복, _pan_last 초기화"""
        self._pan_last = None
        self.canvas.config(cursor="cross")

    def _commit_text(self):
        self._stop_cursor_blink()
        if self._t_buf.strip():
            self.page_data[self.page_index]["texts"].append({
                "text": self._t_buf,
                "rx": self._text_rx, "ry": self._text_ry,
                "color": self.color,
                "font_size": self.settings["font_size"],
            })
            self.undo_stack.append({"page": self.page_index, "type": "text"})
        self._typing = False
        self._t_buf = ""
        self.draw()

    def _cancel_text(self):
        self._stop_cursor_blink()
        self._typing = False
        self._t_buf = ""
        self.draw()

    # ═══════════════════════════════════════════
    # 그리기
    # ═══════════════════════════════════════════
    def draw(self):
        if not self.base_img:
            return
        self.canvas.delete("all")
        dw = int(self.base_img.width * self.zoom)
        dh = int(self.base_img.height * self.zoom)
        self.tk_img = ImageTk.PhotoImage(self.base_img.resize((dw, dh), Image.LANCZOS))
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_img)

        d = self.page_data[self.page_index]
        for edge in d["edges"]:
            x1, y1 = self._to_canvas(*edge["a"])
            x2, y2 = self._to_canvas(*edge["b"])
            self.canvas.create_line(x1, y1, x2, y2,
                                    fill=edge["color"],
                                    width=max(1, int(edge["width"] * self.zoom)),
                                    capstyle=tk.ROUND)
        for m in d["ticks"]:
            cx, cy = self._to_canvas(m["rx"], m["ry"])
            sz = 14 * self.zoom
            w = max(2, int(m["width"] * 0.6 * self.zoom))
            self.canvas.create_line(cx - sz*0.8, cy + sz*0.2, cx, cy + sz, fill=m["color"], width=w)
            self.canvas.create_line(cx, cy + sz, cx + sz*1.2, cy - sz*0.8, fill=m["color"], width=w)
        if self._bell_start_pt:
            bx, by = self._to_canvas(*self._bell_start_pt)
            r = 10 * self.zoom
            self.canvas.create_oval(bx - r, by - r, bx + r, by + r, outline="#ffff00", width=2)
        for t in d["texts"]:
            x, y = self._to_canvas(t["rx"], t["ry"])
            self.canvas.create_text(x, y, text=t["text"], fill=t["color"], anchor=tk.NW,
                                    font=("맑은 고딕", max(8, int(t["font_size"] * self.zoom)), "bold"))

    # ═══════════════════════════════════════════
    # 벨 연결 확인
    # ═══════════════════════════════════════════
    def _check_bell_connection(self, p1, p2):
        edges = self.page_data[self.page_index]["edges"]
        queue, visited, threshold = [p1], set(), 0.025
        while queue:
            curr = queue.pop(0)
            if math.dist(curr, p2) < threshold:
                return True
            for i, eg in enumerate(edges):
                if i not in visited:
                    if math.dist(curr, eg["a"]) < threshold:
                        visited.add(i); queue.append(eg["b"])
                    elif math.dist(curr, eg["b"]) < threshold:
                        visited.add(i); queue.append(eg["a"])
        return False

    # ═══════════════════════════════════════════
    # 우클릭
    # ═══════════════════════════════════════════
    def _on_right_click(self, e):
        if self._typing:
            self._cancel_text()
            return
        # pan 이동 중이면 이동 정지
        if self.mode == "pan" and self._pan_last:
            self._stop_pan()
            return
        self._line_pts = []
        self._bell_start_pt = None
        self.draw()

    def _on_release(self, e):
        """마우스 버튼을 떼면 pan 이동 자동 정지"""
        if self.mode == "pan" and self._pan_last:
            self._stop_pan()

    # ═══════════════════════════════════════════
    # 마우스 이동
    # ═══════════════════════════════════════════
    def _on_move(self, e):
        if self.mode == "pan" and self._pan_last:
            self.offset_x += e.x - self._pan_last[0]
            self.offset_y += e.y - self._pan_last[1]
            self._pan_last = (e.x, e.y)
            self.draw()
            if self._typing:
                self._update_text_view()
        elif self.mode == "pan" and not self._pan_last:
            # 이동 정지 상태 — 커서만 손 모양 유지
            self.canvas.config(cursor="hand2")
        elif self.mode == "line" and self._line_pts:
            self.draw()
            if self._typing:
                self._update_text_view()
            p1c = self._to_canvas(*self._line_pts[-1])
            self.canvas.create_line(p1c[0], p1c[1], e.x, e.y, fill=self.color, dash=(5, 5))

    # ═══════════════════════════════════════════
    # 휠 줌
    # ═══════════════════════════════════════════
    def _on_wheel(self, e):
        old_z = self.zoom
        self.zoom = max(0.1, min(self.zoom * (1.1 if e.delta > 0 else 0.9), 10.0))
        self.offset_x = e.x - (e.x - self.offset_x) * (self.zoom / old_z)
        self.offset_y = e.y - (e.y - self.offset_y) * (self.zoom / old_z)
        self.draw()
        if self._typing:
            self._update_text_view()

    # ═══════════════════════════════════════════
    # 파일 로드
    # ═══════════════════════════════════════════
    def load_file(self, path):
        try:
            self.file_path = path
            self.is_pdf = path.lower().endswith(".pdf")
            self.pdf = fitz.open(path) if self.is_pdf else None
            self.page_count = len(self.pdf) if self.is_pdf else 1
            self.page_index = 0
            # rotation 키도 함께 초기화
            self.page_data = {
                i: {"texts": [], "edges": [], "ticks": [], "rotation": 0}
                for i in range(self.page_count)
            }
            self.settings["default_path"] = path
            self._save_settings()
            self._load_page()
            self.after(100, self.fit_to_window)
        except Exception as ex:
            messagebox.showerror("파일 오류", str(ex))

    def _load_page(self):
        """원본 이미지 로드 후 현재 rotation 적용"""
        if self.is_pdf:
            pix = self.pdf[self.page_index].get_pixmap(matrix=fitz.Matrix(2, 2))
            self._raw_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            self._raw_img = Image.open(self.file_path).convert("RGB")

        rot = self.page_data[self.page_index].get("rotation", 0)
        # PIL rotate: 반시계 방향 → 시계방향 회전은 음수
        self.base_img = self._raw_img.rotate(-rot, expand=True) if rot else self._raw_img.copy()

        self._page_lbl.config(text=f"{self.page_index + 1} / {self.page_count}")
        self._rot_lbl.config(text=f"{rot:>3}°")
        self.draw()

    def fit_to_window(self):
        if not self.base_img:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 50:
            return
        w, h = self.base_img.size
        self.zoom = min(cw / w, ch / h) * 0.95
        self.offset_x = (cw - w * self.zoom) / 2
        self.offset_y = (ch - h * self.zoom) / 2
        self.draw()

    # ═══════════════════════════════════════════
    # Undo
    # ═══════════════════════════════════════════
    def undo(self):
        if not self.undo_stack:
            return
        item = self.undo_stack.pop()
        self.page_data[item["page"]][item["type"] + "s"].pop()
        self.draw()

    # ═══════════════════════════════════════════
    # 저장 — 회전 반영
    # ═══════════════════════════════════════════
    def save_work(self):
        if self._typing:
            self._commit_text()
        now = datetime.datetime.now().strftime("%m%d_%H%M")
        path = filedialog.asksaveasfilename(
            initialfile=f"작업완료_{now}.pdf",
            defaultextension=".pdf",
        )
        if not path:
            return
        try:
            out_pdf = fitz.open(self.file_path) if self.is_pdf else fitz.open()
            if not self.is_pdf:
                page = out_pdf.new_page(width=self._raw_img.width, height=self._raw_img.height)
                page.insert_image(page.rect, filename=self.file_path)

            for i in range(self.page_count):
                page = out_pdf[i]
                d = self.page_data[i]
                rot = d.get("rotation", 0)

                # PDF 페이지 자체를 회전 (PyMuPDF 내장 기능)
                # set_rotation은 0/90/180/270만 지원
                if rot in (0, 90, 180, 270):
                    page.set_rotation(rot)

                # 회전 후 실제 렌더 크기 기준으로 좌표 재계산
                pw, ph = page.rect.width, page.rect.height

                for edge in d["edges"]:
                    rgb = [int(edge["color"][j:j+2], 16) / 255 for j in (1, 3, 5)]
                    page.draw_line(
                        fitz.Point(edge["a"][0] * pw, edge["a"][1] * ph),
                        fitz.Point(edge["b"][0] * pw, edge["b"][1] * ph),
                        color=rgb, width=edge["width"],
                    )
                for m in d["ticks"]:
                    rgb = [int(m["color"][j:j+2], 16) / 255 for j in (1, 3, 5)]
                    cx, cy = m["rx"] * pw, m["ry"] * ph
                    page.draw_line(fitz.Point(cx - 8, cy + 2),   fitz.Point(cx, cy + 10),     color=rgb, width=2.5)
                    page.draw_line(fitz.Point(cx, cy + 10),      fitz.Point(cx + 12, cy - 8), color=rgb, width=2.5)
                for t in d["texts"]:
                    rgb = [int(t["color"][j:j+2], 16) / 255 for j in (1, 3, 5)]
                    page.insert_text(
                        (t["rx"] * pw, t["ry"] * ph + t["font_size"]),
                        t["text"], fontsize=t["font_size"], color=rgb,
                    )
            out_pdf.save(path)
            out_pdf.close()
            messagebox.showinfo("저장", "저장 성공!")
        except Exception as ex:
            messagebox.showerror("저장 오류", str(ex))

    # ═══════════════════════════════════════════
    # 설정 창
    # ═══════════════════════════════════════════
    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("⚙️ 설정")
        win.geometry("320x240")
        win.resizable(False, False)
        win.configure(bg="#1a1a2e")

        lbl_style = {"bg": "#1a1a2e", "fg": "#ccccdd", "font": ("맑은 고딕", 10)}
        ent_style = {"bg": "#2a2a3e", "fg": "#ffffff", "insertbackground": "#ffffff",
                     "relief": tk.FLAT, "font": ("Consolas", 11), "width": 8}

        tk.Label(win, text="⚙️ 환경 설정", bg="#1a1a2e", fg="#00ffcc",
                 font=("맑은 고딕", 12, "bold")).pack(pady=(14, 8))

        row1 = tk.Frame(win, bg="#1a1a2e"); row1.pack(fill=tk.X, padx=30, pady=4)
        tk.Label(row1, text="✏ 선 굵기 (1~30):", **lbl_style).pack(side=tk.LEFT)
        e_width = tk.Entry(row1, **ent_style); e_width.pack(side=tk.RIGHT)
        e_width.insert(0, str(self.settings["line_width"]))

        row2 = tk.Frame(win, bg="#1a1a2e"); row2.pack(fill=tk.X, padx=30, pady=4)
        tk.Label(row2, text="🔤 글자 크기 (8~72):", **lbl_style).pack(side=tk.LEFT)
        e_font = tk.Entry(row2, **ent_style); e_font.pack(side=tk.RIGHT)
        e_font.insert(0, str(self.settings["font_size"]))

        def apply_settings():
            try:
                lw = int(e_width.get())
                fs = int(e_font.get())
                if not (1 <= lw <= 30): raise ValueError("선 굵기 범위 초과")
                if not (8 <= fs <= 72): raise ValueError("글자 크기 범위 초과")
                self.settings["line_width"] = lw
                self.settings["font_size"] = fs
                self._width_var.set(lw); self._width_lbl.config(text=f"{lw}px")
                self._font_var.set(fs);  self._font_lbl.config(text=f"{fs}pt")
                self._save_settings()
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("입력 오류", str(ve), parent=win)

        tk.Button(win, text="✔ 저장", command=apply_settings,
                  bg="#2e4a2e", fg="#ffffff", relief=tk.FLAT,
                  font=("맑은 고딕", 10, "bold"), padx=20, pady=6).pack(pady=14)

    # ═══════════════════════════════════════════
    # 도움말
    # ═══════════════════════════════════════════
    def show_help(self):
        messagebox.showinfo(
            "도움말",
            "[ 도구 사용법 ]\n"
            "🖐 이동    : 드래그로 도면 이동\n"
            "📏 직선결선: 클릭→클릭 (수평/수직 자동 snap)\n"
            "           선 완성 시 양 끝 마킹 자동 삭제\n"
            "🔤 문자    : 클릭 후 바로 입력, Enter=확정, Esc=취소\n"
            "✔️ 마킹    : 클릭 위치에 체크 마킹 추가\n"
            "🔔 벨테스트: 두 점 클릭 → 연결 확인 시 비프음\n\n"
            "[ 도면 회전 ]\n"
            "↺ 좌 90° / ↻ 우 90° / ↕ 180° 버튼 클릭\n"
            "단축키: Ctrl+L(좌회전), Ctrl+R(우회전)\n"
            "페이지별 독립 회전 / 저장 시 PDF에 반영\n\n"
            "[ 단축키 ]\n"
            "휠        : 확대/축소\n"
            "우클릭    : 직선 취소 (모드 유지)\n"
            "Ctrl+Z    : 마지막 작업 취소\n"
            "Ctrl+L    : 도면 좌회전 90°\n"
            "Ctrl+R    : 도면 우회전 90°\n"
            "Esc       : 텍스트 입력 취소"
        )

    # ═══════════════════════════════════════════
    # 기타
    # ═══════════════════════════════════════════
    def reset_work(self):
        if self._typing:
            self._cancel_text()
        rot = self.page_data[self.page_index].get("rotation", 0)
        self.page_data[self.page_index] = {"texts": [], "edges": [], "ticks": [], "rotation": rot}
        self.draw()

    def open_file_dialog(self):
        p = filedialog.askopenfilename(
            filetypes=[("PDF / 이미지", "*.pdf *.png *.jpg *.jpeg *.bmp"), ("모든 파일", "*.*")]
        )
        if p:
            self.load_file(p)

    def _choose_color(self):
        c = colorchooser.askcolor(color=self.color)[1]
        if c:
            self.color = c
            self._color_preview.config(bg=c)

    def prev_page(self):
        if self._typing:
            self._commit_text()
        if self.page_index > 0:
            self.page_index -= 1
            self._load_page()

    def next_page(self):
        if self._typing:
            self._commit_text()
        if self.page_index < self.page_count - 1:
            self.page_index += 1
            self._load_page()

    # ═══════════════════════════════════════════
    # 좌표 변환
    # ═══════════════════════════════════════════
    def _to_ratio(self, cx, cy):
        return (
            (cx - self.offset_x) / (self.base_img.width * self.zoom),
            (cy - self.offset_y) / (self.base_img.height * self.zoom),
        )

    def _to_canvas(self, rx, ry):
        return (
            rx * self.base_img.width * self.zoom + self.offset_x,
            ry * self.base_img.height * self.zoom + self.offset_y,
        )

    # ═══════════════════════════════════════════
    # 이벤트 바인딩
    # ═══════════════════════════════════════════
    def _bind_events(self):
        self.canvas.bind("<Button-1>",        self._on_click)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)   # 마우스 버튼 뗄 때 이동 정지
        self.canvas.bind("<Button-3>",        self._on_right_click)
        self.canvas.bind("<Motion>",          self._on_move)
        self.canvas.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<Key>",                    self._on_key)
        self.bind("<Control-z>",              lambda e: self.undo())
        self.bind("<Control-l>",              lambda e: self.rotate_page(-90))
        self.bind("<Control-r>",              lambda e: self.rotate_page(90))


if __name__ == "__main__":
    App().mainloop()
