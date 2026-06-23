"""
workflow_view.py
今の設定から組み立てた ComfyUI ワークフロー（ノード配線）を見る/書き出すウィンドウ。

学習用に2つの見方を1つの窓にまとめている。
  - ① アプリ内にノード配線図を描画（ボックス＋配線。設定を変えると中身が変わる）
  - ② 「JSONを保存」で API 形式のワークフローを書き出し → 本物の ComfyUI で開いて学ぶ

依存は標準の tkinter.Canvas のみ（追加インストール不要）。
"""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

PINK = {
    "window": "#fdeaf3",
    "panel": "#f8dbe8",
    "button": "#db3b8f",
    "button_hover": "#c02e7b",
    "accent": "#3f94d1",
    "node": "#ffffff",
    "node_edge": "#db3b8f",
    "node_hi": "#7c3aed",
    "wire": "#c08aa6",
    "wire_label": "#9a6b85",
    "title": "#7a3b5a",
    "sub": "#555555",
}

NODE_W, NODE_H = 178, 70
HGAP, VGAP = 86, 28
MARGIN = 28


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _layout(workflow: dict) -> dict[str, int]:
    """各ノードの「列（depth）」を、入力をたどった最長経路で決める。"""
    deps: dict[str, list[str]] = {}
    for nid, node in workflow.items():
        srcs = [v[0] for v in node.get("inputs", {}).values() if _is_link(v) and v[0] in workflow]
        deps[nid] = srcs

    depth: dict[str, int] = {}

    def calc(nid: str, stack: tuple = ()) -> int:
        if nid in depth:
            return depth[nid]
        if nid in stack:  # 循環ガード
            return 0
        srcs = deps.get(nid, [])
        depth[nid] = (max((calc(s, stack + (nid,)) for s in srcs), default=-1) + 1) if srcs else 0
        return depth[nid]

    for nid in workflow:
        calc(nid)
    return depth


def _node_subtitle(node: dict) -> str:
    """ノードの設定値（リンクでない入力）を短くまとめる。"""
    parts = []
    for k, v in node.get("inputs", {}).items():
        if _is_link(v):
            continue
        if k == "text":
            s = str(v).strip().replace("\n", " ")
            parts.append(f'"{s[:22]}…"' if len(s) > 22 else f'"{s}"')
        else:
            s = str(v)
            if len(s) > 18:
                s = s[:17] + "…"
            parts.append(f"{k}={s}")
    return "  ".join(parts)


class WorkflowWindow(ctk.CTkToplevel):
    """ノード配線図 ＋ JSON 書き出し。"""

    def __init__(self, parent, workflow: dict, save_dir, caption: str = ""):
        super().__init__(parent)
        self.title("ワークフロー（ノード配線）" + (f" - {caption}" if caption else ""))
        self.geometry("1120x780")
        self.configure(fg_color=PINK["window"])
        self._workflow = workflow
        self._save_dir = Path(save_dir)
        self._build()
        self._draw()

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color=PINK["panel"])
        bar.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(
            bar,
            text="今の設定で ComfyUI に送られるノード配線です。左→右に処理が流れます。",
            anchor="w", text_color=PINK["title"],
        ).pack(side="left", padx=10, pady=8)
        ctk.CTkButton(bar, text="📄 JSONを表示", width=110, command=self._toggle_json,
                      fg_color=PINK["accent"], hover_color=PINK["button_hover"]).pack(side="right", padx=(4, 10), pady=6)
        ctk.CTkButton(bar, text="💾 JSONを保存", width=130, command=self._save_json,
                      fg_color=PINK["button"], hover_color=PINK["button_hover"]).pack(side="right", padx=4, pady=6)

        # ── キャンバス（スクロール可能）──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._canvas = tk.Canvas(body, bg=PINK["window"], highlightthickness=0)
        ysb = ctk.CTkScrollbar(body, command=self._canvas.yview)
        xsb = ctk.CTkScrollbar(body, orientation="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        # ── JSON 表示（初期は隠す）──
        self._json_box = ctk.CTkTextbox(self, height=200, wrap="none")
        self._json_visible = False

    # ── 図の描画 ──

    def _draw(self):
        wf = self._workflow
        depth = _layout(wf)
        cols: dict[int, list[str]] = {}
        for nid, d in depth.items():
            cols.setdefault(d, []).append(nid)
        for c in cols.values():
            c.sort(key=lambda x: int(x) if str(x).isdigit() else 0)

        pos: dict[str, tuple[int, int]] = {}
        for d in sorted(cols):
            for i, nid in enumerate(cols[d]):
                x = MARGIN + d * (NODE_W + HGAP)
                y = MARGIN + i * (NODE_H + VGAP)
                pos[nid] = (x, y)

        cv = self._canvas
        small = ("", 8)
        bold = ("", 10, "bold")

        # 配線（ノードの下に描く）
        for nid, node in wf.items():
            dx, dy = pos[nid]
            links = [(k, v) for k, v in node.get("inputs", {}).items() if _is_link(v) and v[1] is not None and v[0] in pos]
            n = len(links)
            for j, (key, v) in enumerate(links):
                sx, sy = pos[v[0]]
                x1, y1 = sx + NODE_W, sy + NODE_H / 2
                x2 = dx
                y2 = dy + NODE_H * (j + 1) / (n + 1)
                cv.create_line(x1, y1, x1 + 22, y1, x2 - 22, y2, x2, y2,
                               fill=PINK["wire"], width=2, arrow=tk.LAST, smooth=True)
                cv.create_text(x2 - 6, y2 - 7, text=key, anchor="e", fill=PINK["wire_label"], font=small)

        # ノード
        for nid, node in wf.items():
            x, y = pos[nid]
            ctype = node.get("class_type", "?")
            hi = ctype == "KSampler"
            cv.create_rectangle(x, y, x + NODE_W, y + NODE_H, fill=PINK["node"],
                                outline=PINK["node_hi"] if hi else PINK["node_edge"],
                                width=3 if hi else 1)
            cv.create_text(x + 9, y + 9, text=f"{ctype}", anchor="nw", fill=PINK["title"], font=bold)
            sub = _node_subtitle(node)
            if sub:
                cv.create_text(x + 9, y + 31, text=sub, anchor="nw", fill=PINK["sub"],
                               font=small, width=NODE_W - 18)

        bbox = cv.bbox("all")
        if bbox:
            cv.configure(scrollregion=(0, 0, bbox[2] + MARGIN, bbox[3] + MARGIN))

    # ── JSON ──

    def _toggle_json(self):
        if self._json_visible:
            self._json_box.pack_forget()
            self._json_visible = False
            return
        self._json_box.delete("1.0", "end")
        self._json_box.insert("1.0", json.dumps(self._workflow, ensure_ascii=False, indent=2))
        self._json_box.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self._json_visible = True

    def _save_json(self):
        self._save_dir.mkdir(parents=True, exist_ok=True)
        path = self._save_dir / f"workflow_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._workflow, f, ensure_ascii=False, indent=2)
        from tkinter import messagebox
        messagebox.showinfo(
            "保存しました",
            f"ワークフロー(API形式)を保存しました：\n{path}\n\n"
            "ComfyUI で開くには：新しめの ComfyUI なら、この .json を\n"
            "ComfyUI の画面にドラッグ＆ドロップすると配線が復元されます。\n"
            "（復元できない古い版では、このアプリのノード図で学べます）",
        )
