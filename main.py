# -*- coding: utf-8 -*-
"""
ETF 溢价监控 · 安卓版（Kivy）

功能
  · 近 100 交易日溢价曲线（按「美股QDII / 港股中概 / 黄金商品 / 债券货币 / A股ETF」分色）
  · 最近交易日溢价榜（代码、名称、溢价率、收盘价、单位净值）
  · 3% 告警线；分组筛选；下拉刷新数据；本地缓存，断网可看上次结果
  · 首次启动自动下载 100 天数据（需要联网，约 30~90 秒）

说明
  不含后台常驻服务：安卓 8+ 对后台网络限制严格，本 App 采用「打开即刷新」，
  轻量、省电、不会被系统杀进程。数据为日频（收盘价 + 单位净值），
  不是盘中实时 IOPV；日内实时监控请继续用桌面版 ETFdeal.py。
"""
import os
import threading
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel, LabelBase
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.utils import platform

import etf_data as D

# 中文字体：把 assets/NotoSansSC-Regular.otf 打进包里；缺失时退回系统默认（中文会显示成方框）
_FONT = None
for _name in ("NotoSansSC-Regular.otf", "NotoSansSC-Regular.ttf"):
    _p = os.path.join("assets", _name)
    if os.path.exists(_p):
        LabelBase.register(name="CJK", fn_regular=_p)
        _FONT = "CJK"
        break

FONT_KW = {"font_name": _FONT} if _FONT else {}


def L(text, **kw):
    kw.setdefault("font_size", sp(13))
    kw.update(FONT_KW)
    return Label(text=text, **kw)


def B(text, **kw):
    kw.setdefault("font_size", sp(12))
    kw.update(FONT_KW)
    return Button(text=text, **kw)


class Chart(Widget):
    """溢价曲线：自绘坐标轴 + 折线（不依赖 matplotlib/numpy）"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.data = {}
        self.visible = set(D.GROUPS.keys())
        self.last_date = ""
        self.window_days = D.DAYS
        self._labels = {}
        self.bind(size=lambda *a: self.redraw(), pos=lambda *a: self.redraw())

    def set_data(self, data, last_date=""):
        self.data = data or {}
        self.last_date = last_date
        self.redraw()

    # ---- 工具 ----
    def _text(self, canvas, s, x, y, size=11, color=(0.25, 0.25, 0.28, 1)):
        key = (s, size, color)
        lab = self._labels.get(key)
        if lab is None:
            lab = CoreLabel(text=s, font_size=sp(size), color=color,
                            **({"font_name": _FONT} if _FONT else {}))
            lab.refresh()
            self._labels[key] = lab
        tex = lab.texture
        Rectangle(pos=(x, y), size=tex.size, texture=tex)
        canvas.add(Rectangle(pos=(x, y), size=tex.size, texture=tex))

    def _series(self):
        """收集可见分组下所有序列，返回 [(code, name, color, dates, premiums)]"""
        out = []
        for g in D.GROUPS:
            if g not in self.visible:
                continue
            base = D.COLORS[g]
            for i, code in enumerate(D.GROUPS[g]):
                s = self.data.get(code)
                if not s or not s.get("premium"):
                    continue
                shade = 1 - 0.28 * (i % 3)          # 同组内用深浅区分
                col = (base[0] * shade, base[1] * shade, base[2] * shade, 1)
                out.append((code, D.NAMES.get(code, code), col, s["dates"], s["premium"]))
        return out

    # ---- 绘制 ----
    def redraw(self):
        self.canvas.clear()
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.96, 0.97, 0.98, 1)
            Rectangle(pos=self.pos, size=self.size)

            if not self.data:
                self._text(self.canvas, "暂无数据，点「刷新」下载", self.x + dp(20),
                           self.center_y, 13, (0.45, 0.45, 0.5, 1))
                return

            series = self._series()
            if not series:
                self._text(self.canvas, "当前分组无数据", self.x + dp(20),
                           self.center_y, 13, (0.45, 0.45, 0.5, 1))
                return

            left, right = self.x + dp(44), self.right - dp(10)
            bottom, top = self.y + dp(30), self.top - dp(42)
            w, h = right - left, top - bottom

            # 联合日期轴：不同标的最后一天可能不同（QDII 净值慢一天），按日期对齐
            dates = sorted({d for s in series for d in s[3]})[-self.window_days:]
            xs = {d: i for i, d in enumerate(dates)}
            n = len(dates)
            val_map = {}
            for code, name, col, ds, ps in series:
                val_map[code] = {d: v for d, v in zip(ds, ps) if d in xs}

            # Y 轴范围：只看可见曲线，留出 3% 线
            sample = list(val_map.values())
            allv = [v for s in sample for v in s.values()]
            lo = min(allv + [0]) - 1
            hi = max(allv + [D.THRESHOLD]) + 1
            span = (hi - lo) or 1

            def ypx(v):
                return bottom + (v - lo) / span * h

            def xpx(i):
                return left + (i / (n - 1) * w if n > 1 else w / 2)

            # 网格 + Y 刻度（从绘图区内第一个整刻度开始，避免画到框外）
            step = 5 if span > 20 else (2 if span > 8 else 1)
            v = ((int(lo) + step - 1) // step) * step
            while v <= hi:
                if v == 0:
                    Color(0.55, 0.57, 0.62, 1)
                    Line(points=[left, ypx(0), right, ypx(0)], width=1.0)
                else:
                    Color(0.88, 0.89, 0.92, 1)
                    Line(points=[left, ypx(v), right, ypx(v)], width=0.7)
                if lo <= v <= hi:
                    self._text(self.canvas, f"{v}%", self.x + dp(4), ypx(v) - dp(6), 9,
                               (0.5, 0.5, 0.55, 1))
                v += step

            # 3% 告警线
            Color(0.86, 0.2, 0.2, 1)
            Line(points=[left, ypx(D.THRESHOLD), right, ypx(D.THRESHOLD)],
                 width=1.3, dash_length=5, dash_offset=3)
            self._text(self.canvas, f"{D.THRESHOLD}% 告警", left + dp(2),
                       ypx(D.THRESHOLD) + dp(3), 9, (0.86, 0.2, 0.2, 1))

            # X 轴日期
            tick = max(1, n // 5)
            for i in range(0, n, tick):
                Color(0.90, 0.91, 0.94, 1)
                Line(points=[xpx(i), bottom, xpx(i), top], width=0.6)
                self._text(self.canvas, dates[i][5:], xpx(i) - dp(13),
                           self.y + dp(8), 9, (0.5, 0.5, 0.55, 1))

            # 折线（缺值断开，不把断点连成直线）
            for code, name, col, ds, ps in series:
                Color(*col)
                pts, seg_open = [], False
                for i, d in enumerate(dates):
                    vv = val_map[code].get(d)
                    if vv is None:
                        if len(pts) >= 4:
                            Line(points=pts, width=1.1)
                        pts, seg_open = [], False
                        continue
                    pts += [xpx(i), ypx(vv)]
                    seg_open = True
                if seg_open and len(pts) >= 4:
                    Line(points=pts, width=1.1)

            # 图例
            lx, ly = left + dp(2), self.top - dp(20)
            for g in D.GROUPS:
                if g not in self.visible:
                    continue
                c = D.COLORS[g]
                Color(*c)
                Rectangle(pos=(lx, ly), size=(dp(9), dp(3)))
                self._text(self.canvas, g, lx + dp(12), ly - dp(7), 8, (0.35, 0.35, 0.4, 1))
                lx += dp(24) + len(g) * dp(8)


class ETFApp(App):
    title = "ETF 溢价监控"

    def build(self):
        self.base_dir = self.user_data_dir if platform == "android" else os.path.abspath(".")
        self.status = "启动中…"
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        # 标题 + 状态
        head = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        head.add_widget(L("ETF 溢价监控 · 日频", bold=True, font_size=sp(16),
                          halign="left"))
        self.lbl_status = L("", font_size=sp(11), halign="right", color=(0.4, 0.4, 0.45, 1))
        head.add_widget(self.lbl_status)
        root.add_widget(head)

        # 分组筛选
        bar = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(3))
        self.grp_btns = {}
        for g in D.GROUPS:
            b = B(g, background_color=(0.25, 0.45, 0.8, 1))
            b.bind(on_release=lambda inst, gg=g: self.toggle_group(gg))
            self.grp_btns[g] = b
            bar.add_widget(b)
        root.add_widget(bar)

        # 图表
        self.chart = Chart(size_hint_y=1)
        root.add_widget(self.chart)

        # 结论区
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(96), spacing=dp(2))
        self.lbl_date = L("", font_size=sp(12), bold=True, halign="left")
        self.lbl_top = L("", font_size=sp(11), halign="left")
        self.lbl_warn = L("", font_size=sp(11), halign="left", color=(0.8, 0.25, 0.2, 1))
        for w in (self.lbl_date, self.lbl_top, self.lbl_warn):
            box.add_widget(w)
        root.add_widget(box)

        # 操作区
        ops = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b_refresh = B("刷新数据", background_color=(0.2, 0.55, 0.35, 1))
        b_refresh.bind(on_release=lambda *a: self.refresh(force=True))
        self.b_zoom = B("近20日", background_color=(0.35, 0.35, 0.4, 1))
        self.b_zoom.bind(on_release=lambda *a: self.toggle_zoom())
        b_about = B("说明", background_color=(0.45, 0.45, 0.5, 1))
        b_about.bind(on_release=lambda *a: self.show_about())
        ops.add_widget(b_refresh)
        ops.add_widget(self.b_zoom)
        ops.add_widget(b_about)
        root.add_widget(ops)

        Clock.schedule_once(lambda *a: self.boot(), 0.4)
        return root

    # ---- 启动 ----
    def boot(self):
        cache = D.load_cache(self.base_dir)
        if cache and cache.get("data"):
            self.apply(cache["data"], cache.get("updated", ""))
            self.set_status("缓存 %s" % cache.get("updated", "")[:16])
            # 缓存超过 12 小时则后台静默更新
            try:
                age = (datetime.now() - datetime.strptime(cache["updated"],
                                                          "%Y-%m-%d %H:%M:%S")).total_seconds()
            except Exception:
                age = 1e9
            if age > 12 * 3600 and platform != "android":
                self.refresh()
            elif age > 3 * 24 * 3600:
                self.refresh()
        else:
            self.set_status("首次启动，正在下载 100 天数据…")
            self.refresh(force=True, redownload=True)

    def set_status(self, txt):
        self.status = txt
        self.lbl_status.text = txt

    def toggle_group(self, g):
        if g in self.chart.visible:
            if len(self.chart.visible) == 1:
                return
            self.chart.visible.discard(g)
            self.grp_btns[g].background_color = (0.6, 0.6, 0.62, 1)
        else:
            self.chart.visible.add(g)
            self.grp_btns[g].background_color = (0.25, 0.45, 0.8, 1)
        self.chart.redraw()

    def toggle_zoom(self):
        if self.chart.window_days >= D.DAYS:
            self.chart.window_days, self.b_zoom.text = 20, "近100日"
        else:
            self.chart.window_days, self.b_zoom.text = D.DAYS, "近20日"
        self.chart.redraw()
        n_days = max((len(s["dates"]) for s in self.chart.data.values()), default=0)
        self.set_status("覆盖 %d 只 / %s" % (len(self.chart.data),
                                           "近20日" if self.chart.window_days == 20
                                           else "近%d天" % min(n_days, D.DAYS)))

    # ---- 刷新 ----
    def refresh(self, force=False, redownload=False):
        if getattr(self, "_busy", False):
            return
        self._busy = True
        self.set_status("正在联网下载…")
        days = D.DAYS if redownload else D.DAYS
        threading.Thread(target=self._worker, args=(days,), daemon=True).start()

    def _worker(self, days):
        def prog(i, total, code, ok, msg):
            def upd(*a):
                self.set_status("下载 %d/%d %s %s" % (i, total, code, "OK" if ok else msg))
            Clock.schedule_once(upd, 0)
        try:
            data = D.fetch_all(days, progress=prog)
            if not data:
                raise RuntimeError("全部接口失败，检查网络")
            D.save_cache(self.base_dir, data, days)
            Clock.schedule_once(lambda *a: self._done(data, True), 0)
        except Exception as e:
            Clock.schedule_once(lambda *a: self._fail(str(e)), 0)

    def _fail(self, msg):
        self._busy = False
        self.set_status("下载失败：%s" % msg)
        cache = D.load_cache(self.base_dir)
        if cache and cache.get("data"):
            self.apply(cache["data"], cache.get("updated", ""))

    def _done(self, data, ok):
        self._busy = False
        self.apply(data, datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.set_status("已更新 · %d 只 / %d 天" % (len(data), D.DAYS))

    def apply(self, data, updated=""):
        last, rows = D.latest_stats(data)
        self.chart.set_data(data, last)
        if rows:
            t = rows[0]
            self.lbl_date.text = "最高溢价：%s %s  %.2f%%（%s）" % (
                t["code"], t["name"], t["premium"], t["date"])
            self.lbl_top.text = "收盘 %.3f / 净值 %.3f ｜ 数据日 %s" % (
                t["price"], t["nav"], last or "-")
            over = [r for r in rows if r["premium"] >= D.THRESHOLD]
            if over:
                head = "、".join("%s %.1f%%" % (r["name"], r["premium"])
                                for r in over[:2])
                self.lbl_warn.text = "超 %.0f%% 共 %d 只：%s%s" % (
                    D.THRESHOLD, len(over), head, " 等" if len(over) > 2 else "")
            else:
                self.lbl_warn.text = "全部标的最新溢价均在 %.0f%% 以下" % D.THRESHOLD
        n_days = max((len(s["dates"]) for s in data.values()), default=0)
        self.set_status("覆盖 %d 只 / %d 天" % (len(data), n_days))

    def show_about(self):
        from kivy.uix.popup import Popup
        msg = ("数据：最近 100 个交易日日频\n"
               "溢价 =(不复权收盘价-单位净值)/单位净值\n"
               "单位净值来自基金公司披露，QDII 有时滞；\n"
               "本工具仅做统计展示，不构成投资建议。\n"
               "缓存目录：%s") % self.base_dir
        pop = Popup(title=L("说明", font_size=sp(14)), size_hint=(0.9, 0.55),
                    content=L(msg, font_size=sp(11), halign="left", valign="top"))
        pop.open()


if __name__ == "__main__":
    ETFApp().run()
