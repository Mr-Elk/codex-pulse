"""Codex Pulse floating Windows strip. No browser or HTTP service required."""
from __future__ import annotations

import argparse
from collections import OrderedDict
import base64
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import traceback

from overlay_geometry import Rect, place, remember, stable_position, resize_from_left
from overlay_stability import Motion
import overlay_settings as preferences
import overlay_style as style
import thread_catalog
import theme
from font_policy import family as ui_font_family
from active_chat import Binding
from pulse import Monitor
from context_probe import PersistentProbe, parse_context
from snapshot_cache import SnapshotCache
from runtime_state import RuntimeSession, atomic_json

BASE = Path(__file__).resolve().parent
VERSION = json.loads((BASE / "plugin.json").read_text(encoding="utf-8"))["version"]


def find_context(hwnd):
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(BASE / "composer_anchor.ps1"), "-WindowHandle", str(hwnd), "-IncludeChat"],
            capture_output=True, text=True, encoding="utf-8-sig", timeout=4, creationflags=subprocess.CREATE_NO_WINDOW)
        value = json.loads(completed.stdout.strip())
        if completed.returncode != 0 or not isinstance(value,dict):
            raise ValueError("Unavailable window context")
        return parse_context(value)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return None, None, "unavailable", None


def find_composer(hwnd):
    return find_context(hwnd)[0]


class Overlay:
    def __init__(self, args):
        import tkinter as tk
        import native_windows as win
        from strip_renderer import render
        self.win, self.tk = win, tk
        self.render_strip = render
        self.args = args
        self.runtime = getattr(args, "runtime", None)
        self.target = win.select_window(args.target_hwnd)
        self.snapshot = None
        self.cache = SnapshotCache()
        self.probe = PersistentProbe()
        self.metrics_wake = threading.Event()
        self.context_at = 0
        self.applied_bounds = None
        self.placement_context = None
        self.position_updates = 0
        self.settings_panel = None
        self.opacity = 0
        self.avoid_rect = None
        self.drag_origin = None
        self.drag_moved = False
        initial_title = next((item["title"] for item in thread_catalog.recent(args.codex_home.resolve(),limit=None,include_archived=True) if item["id"] == args.thread_id), (args.thread_id or "")[:8]) if args.fixed else ""
        self.binding = Binding().pin(args.thread_id, initial_title) if args.fixed else Binding()
        self.args.thread_id = self.binding.identity
        self.bound_title = self.binding.title
        self.composer = None
        self.current_composer = None
        self.last_bounds = None
        self.anchor_window_rect = None
        self.anchor_at = 0
        self.placement_mode = "waiting"
        self.results = queue.Queue()
        self.stop = threading.Event()
        self.drag = None
        self.menu_open = False
        self.hovered = False
        self.hover_control = None
        self.visible = False
        self.interaction_open = None
        self.hidden_reason = "checking_context"
        self.next_target_probe = 0
        saved = preferences.load(args.settings_file, args.legacy_position_file or BASE / "pulse-position.json")
        self.theme_color = theme.activate(theme.load(args.settings_file))
        self.manual = saved["position"]
        self.font_size = saved["font_size"]
        self.locked = saved["locked"] and not args.edit
        self.visible_metrics = tuple(saved["visible_metrics"])
        display = preferences.load_display(args.settings_file)
        self.display_mode, self.desktop_position = display["mode"], display["position"]
        self.compact, self.animations = display["compact"], display["animations"]
        self.expanded_mode = display["expanded_mode"]
        self.motion = Motion(0.18 if self.animations else 0)
        self.passthrough = None
        self.settings_error = False
        previous_foreground = win.user32.GetForegroundWindow()
        self.root = tk.Tk()
        self.root.report_callback_exception = self.callback_exception
        self.root.withdraw()
        self.root.title("Codex Pulse — " + (self.binding.identity or "自动跟随")[:8])
        self.root.overrideredirect(True)
        self.root.configure(bg="#ffffff")
        self.scale = win.dpi(self.target["hwnd"]) if self.target else 1
        self.height = round(style.HEIGHT * self.scale * self.font_size/15)
        self.canvas = tk.Canvas(self.root, bg="#ffffff", highlightthickness=0, bd=0,
                                width=round(self.desired_width()*self.scale*self.font_size/15), height=self.height)
        self.image = None
        self.image_item = None
        self.render_error = None
        self.layout = []
        self.canvas.pack(fill="both", expand=True)
        self.root.update_idletasks()
        self.hwnd = win.top_level(self.root.winfo_id())
        win.decorate_overlay(self.hwnd, self.target["hwnd"] if self.target else None)
        win.restore_startup_focus(self.hwnd, previous_foreground)
        from native_surface import Surface
        self.surface = Surface(self.hwnd, self.target["hwnd"] if self.target and self.display_mode == "composer" else None,
                               input_hwnd=self.root.winfo_id())
        # Native layered pixels have a single owner. An unmapped Tk canvas
        # cannot paint a blank background over them when settings take focus.
        self.canvas.pack_forget()
        self.input_widget = self.root
        if self.display_mode == "desktop":
            win.own_overlay(self.hwnd,None)
            if self.surface.material.hwnd:win.set_floating(self.surface.material.hwnd,True)
            win.set_floating(self.hwnd,True)
        self.refresh_input_mode(False)
        self.input_widget.bind("<ButtonPress-1>", self.drag_start)
        self.input_widget.bind("<B1-Motion>", self.drag_move)
        self.input_widget.bind("<ButtonRelease-1>", self.drag_end)
        self.input_widget.bind("<Button-3>", self.context_menu)
        self.input_widget.bind("<Enter>", lambda _: self.set_hover(True))
        self.input_widget.bind("<Leave>", lambda _: self.set_hover(False))
        self.input_widget.bind("<Motion>", lambda _: self.refresh_input_mode(
            bool(self.target and self.win.active_target(self.target["hwnd"]))))
        self.root.bind("<Escape>", lambda _: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.follow_choice = tk.BooleanVar(value=self.binding.mode == "auto")
        self.thread_choice = tk.StringVar(value=self.binding.identity or "")
        self.size_choice = tk.IntVar(value=self.font_size)
        self.lock_choice = tk.BooleanVar(value=self.locked)
        self.metric_choices = {key: tk.BooleanVar(value=key in self.visible_metrics) for key in style.ORDER}
        # Keep placement and font choices outside the versioned plugin cache.
        self.save_preferences()
        self.workers = [threading.Thread(target=self.collect_metrics, daemon=True),
                        threading.Thread(target=self.collect_context, daemon=True)]
        for worker in self.workers:
            worker.start()
        self.root.after(0, self.tick)
        if getattr(args, "open_settings", False):
            self.root.after(300, self.open_settings)
        if args.duration:
            self.root.after(round(args.duration*1000), lambda: self.close("duration_limit"))

    def callback_exception(self, kind, exception, trace):
        if self.runtime:
            self.runtime.fail(exception, "callback_error")
        traceback.print_exception(kind, exception, trace, file=sys.stderr)
        self.close("callback_error")

    def collect_metrics(self):
        monitors = OrderedDict()
        metrics_at, previous = 0, None
        while not self.stop.is_set():
            binding = self.binding
            try:
                current = (binding.identity, binding.revision)
                if current != previous:
                    metrics_at = 0
                    previous = current
                if binding.identity and time.monotonic() >= metrics_at:
                    if binding.identity not in monitors:
                        monitors[binding.identity] = Monitor(self.args.codex_home.resolve(), binding.identity)
                    monitor = monitors[binding.identity]
                    monitors.move_to_end(binding.identity)
                    while len(monitors) > 4:
                        monitors.popitem(last=False)
                    self.results.put(("snapshot", (binding.identity,binding.revision,monitor.snapshot())))
                    metrics_at = time.monotonic()+2
            except Exception:
                self.results.put(("snapshot", (binding.identity,binding.revision,{"available": False})))
                metrics_at = time.monotonic()+2
            self.metrics_wake.wait(0.2)
            self.metrics_wake.clear()

    def collect_context(self):
        catalog = thread_catalog.CatalogCache()
        try:
            while not self.stop.is_set():
                target = self.target
                if target and (self.win.active_target(target["hwnd"]) or self.args.preview):
                    try:
                        before = self.win.client_rect(target["hwnd"])
                        composer,title,status,interaction = self.probe.read(target["hwnd"])
                        window = self.win.client_rect(target["hwnd"])
                        if before != window:
                            composer = None  # A moved host invalidates this absolute UIA rectangle.
                        items = catalog.read(self.args.codex_home.resolve())
                        self.results.put(("context", (target["hwnd"],composer,window,time.monotonic(),title,status,items,interaction,getattr(self.probe,"avoid_rect",None))))
                    except (OSError, ValueError):
                        self.results.put(("context", (target["hwnd"],None,None,time.monotonic(),None,"unavailable",[],None)))
                self.stop.wait(0.25)
        finally:
            self.probe.close()

    def desired_width(self):
        return 220 if self.display_mode == "desktop" and self.compact else style.width_for(self.visible_metrics)

    def refresh_input_mode(self, active):
        active = active or getattr(self,"display_mode","composer") == "desktop"
        control = None
        if active and self.visible and self.last_bounds:
            point = self.win.cursor_position()
            if point is not None:
                rect = self.last_bounds
                control = style.control_at(point[0]-rect.left, point[1]-rect.top,
                                           rect.width, rect.height, self.scale*self.font_size/15)
        modified = bool(active and self.win.edit_modifier_down())
        if control != self.hover_control:
            self.hover_control = control
            getattr(self,"input_widget",self.canvas).configure(cursor="fleur" if control == "drag" else "hand2" if control == "menu" else "")
        editable = not self.locked or self.menu_open or self.drag or modified or control or (
            getattr(self,"display_mode","composer") == "desktop" and self.compact)
        passthrough = not bool(editable)
        if passthrough != self.passthrough:
            self.win.set_passthrough(self.hwnd, passthrough, per_pixel=hasattr(self,"surface"))
            self.passthrough = passthrough
            if passthrough:
                self.hovered = False
        if self.locked and not self.menu_open and not self.drag:
            self.hovered = bool(control or modified)

    def toggle_lock(self):
        self.locked = bool(self.lock_choice.get())
        self.save_preferences()
        self.refresh_input_mode(bool(self.target and self.win.active_target(self.target["hwnd"])))

    def select_metrics(self):
        selected = tuple(key for key in style.ORDER if self.metric_choices[key].get())
        if not selected:
            for key in self.visible_metrics:
                self.metric_choices[key].set(True)
            return
        self.visible_metrics = selected
        self.save_preferences()

    def draw(self, width):
        capsule = getattr(self,"display_mode","composer") == "desktop" and self.compact
        activity = int(time.monotonic()/0.45)%3 if self.snapshot and self.snapshot.get("request_pending") and getattr(self,"animations",True) else 2
        backdrop = bool(hasattr(self,"surface") and self.surface.material.available)
        render_snapshot = {**(self.snapshot or {}), "visible_metrics": self.visible_metrics, "capsule":capsule,"activity_phase":activity,"backdrop":backdrop}
        render_key = (width, self.scale, self.font_size, self.hovered, capsule, activity, backdrop, theme.current(), tuple(style.metrics(render_snapshot).values()))
        if render_key == getattr(self, "render_key", None):
            return
        try:
            png, layout = self.render_strip(render_snapshot, width, self.scale*self.font_size/15, self.hovered)
            if hasattr(self,"surface"):
                # A Tk canvas image schedules a second, competing GDI paint.
                # In the native path the canvas handles input only.
                self.surface.set_image(png)
            else:
                image = self.tk.PhotoImage(master=self.root, data=base64.b64encode(png).decode("ascii"))
                if self.image_item is None:
                    self.image_item = self.canvas.create_image(0, 0, anchor="nw", image=image)
                else:
                    self.canvas.itemconfigure(self.image_item, image=image)
                self.image = image
            self.layout = layout
            self.render_key, self.render_error = render_key, None
        except (OSError, self.tk.TclError) as error:
            if str(error) != self.render_error:
                print("Codex Pulse rendering error: " + str(error), flush=True)
            self.render_error = str(error)

    def set_hover(self, value):
        self.hovered = value
        if self.last_bounds:
            self.draw(self.last_bounds.width)

    def save_preferences(self):
        try:
            display = {"mode":self.display_mode,"position":self.desktop_position,"compact":self.compact,
                       "animations":self.animations,"expanded_mode":getattr(self,"expanded_mode",self.display_mode)}
            preferences.save(self.args.settings_file, self.font_size, self.manual, self.locked, self.visible_metrics,
                             display=display,theme_color=getattr(self,"theme_color",theme.current()))
            self.settings_error = False
        except OSError:
            self.settings_error = True
            print("Codex Pulse could not save preferences; this session still works.", flush=True)

    def set_font_size(self, size):
        self.font_size = size
        self.save_preferences()

    def set_theme_color(self, value):
        previous=theme.current()
        self.theme_color=theme.activate(value)
        self.save_preferences()
        if self.settings_panel:
            self.settings_panel.apply_theme(previous)
        if self.last_bounds:
            self.draw(self.last_bounds.width)

    def set_display_mode(self, mode, *, expanded_mode=None):
        self.expanded_mode = expanded_mode or mode
        if mode == self.display_mode:
            self.save_preferences()
            return
        self.display_mode = mode
        self.placement_context = None
        owner = self.target["hwnd"] if self.target and mode == "composer" else None
        # Demote our windows before attaching an external app owner again.
        material=self.surface.material if hasattr(self,"surface") else None
        self.win.set_floating(self.hwnd,False)
        if material and material.hwnd:self.win.set_floating(material.hwnd,False)
        self.win.own_overlay(self.hwnd, owner)
        self.raise_pending = True
        if hasattr(self,"surface") and self.surface.material.hwnd:
            self.win.own_overlay(self.surface.material.hwnd, owner)
        if mode == "desktop":
            if material and material.hwnd:self.win.set_floating(material.hwnd,True)
            self.win.set_floating(self.hwnd,True)
            self.anchor_desktop_resize()
        self.save_preferences()

    def toggle_compact(self):
        self.expanded_mode = "desktop"
        self.compact = not self.compact
        self.anchor_desktop_resize()
        self.placement_context = None
        self.save_preferences()

    def toggle_capsule(self):
        """Grip click returns to the presentation that the capsule came from."""
        if self.display_mode == "desktop" and self.compact:
            if getattr(self,"expanded_mode","desktop") == "composer":
                self.set_display_mode("composer")
            else:
                self.toggle_compact()
        else:
            previous = self.display_mode
            self.compact = True
            if previous == "composer":
                self.set_display_mode("desktop", expanded_mode="composer")
            else:
                self.expanded_mode = "desktop"
                self.anchor_desktop_resize()
                self.placement_context = None
                self.save_preferences()
        self.update_freshness()

    def anchor_desktop_resize(self):
        if self.display_mode != "desktop" or not self.last_bounds:return
        area=self.win.work_area(self.hwnd)
        if area:
            scale=self.scale*self.font_size/15
            resized=resize_from_left(self.last_bounds,round(self.desired_width()*scale),round(style.HEIGHT*scale))
            self.desktop_position=remember(area,resized,self.scale)

    def toggle_animations(self):
        self.animations = bool(self.animation_choice.get())
        self.motion.duration = 0.18 if self.animations else 0
        self.save_preferences()

    def animate_frame(self):
        rect, alpha, settled = self.motion.sample(time.monotonic())
        if rect is None:
            return True
        self.opacity = alpha
        if alpha == 0:
            if hasattr(self, "surface"):
                self.surface.hide()
            elif self.visible:
                self.win.hide(self.hwnd)
            self.visible = False
            return settled
        if self.applied_bounds is None or (rect.width,rect.height) != (self.applied_bounds.width,self.applied_bounds.height):
            self.root.geometry(f"{rect.width}x{rect.height}{rect.left:+d}{rect.top:+d}")
            self.root.update_idletasks()
        self.draw(rect.width)
        if hasattr(self, "surface"):
            self.surface.present(rect,alpha)
            if getattr(self,"raise_pending",False):
                self.win.show_without_focus(self.hwnd,rect,raise_window=True)
                self.raise_pending = False
        elif rect != self.applied_bounds or not self.visible:
            self.win.show_without_focus(self.hwnd,rect,raise_window=not self.visible)
        if rect != self.applied_bounds:
            self.position_updates += 1
        self.last_bounds = self.applied_bounds = rect
        self.visible = True
        return settled

    def position_overlay(self, rect):
        if self.motion.target_alpha == 0:self.record_visibility("show",None)
        self.motion.retarget(rect,255,time.monotonic())
        return self.animate_frame()

    def record_visibility(self,event,reason):
        foreground=self.win.user32.GetForegroundWindow()
        entry={"at":time.monotonic(),"event":event,"reason":reason,"foreground":foreground,
               "foreground_root_owner":self.win.user32.GetAncestor(foreground,3) if foreground else None,
               "target":self.target["hwnd"] if self.target else None}
        self.visibility_events=(getattr(self,"visibility_events",[])+[entry])[-12:]

    def anchored_bounds(self, window):
        width = round(self.desired_width()*self.font_size/15*self.scale)
        self.height = round(style.HEIGHT*self.scale*self.font_size/15)
        if self.display_mode == "desktop":
            self.current_composer = None
            return place(window,width,self.height,manual=self.desktop_position,scale=self.scale)
        composer = self.composer
        if composer and self.anchor_window_rect:
            old = self.anchor_window_rect
            if old.width == window.width and old.height == window.height:
                dx,dy = window.left-old.left,window.top-old.top
                composer = Rect(composer.left+dx,composer.top+dy,composer.right+dx,composer.bottom+dy)
            elif old.width:
                dx,dy = window.left-old.left,window.bottom-old.bottom
                composer = Rect(window.left+round((composer.left-old.left)/old.width*window.width),
                                composer.top+dy,window.left+round((composer.right-old.left)/old.width*window.width),composer.bottom+dy)
        if composer and self.manual and self.manual.get("anchor") != "composer":
            previous = place(window,width,self.height,composer,self.manual,self.scale)
            self.manual = remember(window,previous,self.scale,composer)
            self.manual["center_ratio"] = max(0,min(1,self.manual["center_ratio"]))
            self.save_preferences()
        self.current_composer = composer
        rect = place(window,width,self.height,composer,self.manual,self.scale)
        self.placement_mode = "desktop_capsule" if self.display_mode == "desktop" and self.compact else "composer_offset" if composer and self.manual else "composer" if composer else "fallback"
        popup = self.avoid_rect
        if popup and rect.left < popup.right and rect.right > popup.left and rect.top < popup.bottom and rect.bottom > popup.top:
            top = max(window.top,popup.top-self.height-round(8*self.scale))
            rect = Rect(rect.left,top,rect.right,top+self.height)
            self.placement_mode = "above_panel"
        return rect

    def tick(self):
        if self.stop.is_set():
            return
        while True:
            try:
                kind,value = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                identity,revision,snapshot = value
                self.apply_snapshot(identity,snapshot,revision)
            elif kind == "context":
                hwnd,composer,window,at,title,status,catalog,interaction,*extra = value
                if not self.target or self.target["hwnd"] != hwnd:
                    continue
                self.context_at = at
                if composer and window:
                    self.composer,self.anchor_window_rect,self.anchor_at = composer,window,at
                self.interaction_open = interaction
                if interaction is False:
                    self.avoid_rect = None
                elif extra and isinstance(extra[0],Rect):
                    self.avoid_rect = extra[0]
                # Unknown identity clears numbers, never the display shell.
                self.apply_binding(self.binding.follow(title,catalog,status))
        if self.target and not self.win.user32.IsWindow(self.target["hwnd"]):
            if self.display_mode == "composer":
                self.close("host_closed")
                return
            self.target = None
            if self.binding.mode == "auto":
                self.apply_binding(self.binding.automatic())
        if not self.target and time.monotonic() >= self.next_target_probe:
            self.target = self.win.select_window(self.args.target_hwnd)
            self.context_at = 0
            if self.target and self.display_mode == "composer":
                self.win.own_overlay(self.hwnd,self.target["hwnd"])
            self.next_target_probe = time.monotonic()+2
        ready = bool(self.target and not self.win.user32.IsIconic(self.target["hwnd"]))
        active = bool(ready and (self.win.active_target(self.target["hwnd"]) or self.win.user32.GetForegroundWindow() == self.hwnd))
        self.refresh_input_mode(active)
        if not active and not self.menu_open and not self.drag and self.binding.mode == "auto" and self.binding.identity:
            self.apply_binding(self.binding.automatic())
        show = self.display_mode == "desktop" or ((active or self.menu_open or self.args.preview or self.drag) and ready)
        settled = True
        if show and not self.drag:
            window = self.win.work_area(self.hwnd) if self.display_mode == "desktop" else self.win.client_rect(self.target["hwnd"])
            if window:
                if self.target and self.display_mode == "composer":
                    self.scale = self.win.dpi(self.target["hwnd"])
                rect = self.anchored_bounds(window)
                context = (window,self.scale,self.font_size,self.visible_metrics,self.display_mode,self.compact)
                if context == self.placement_context:
                    rect = stable_position(self.motion.target or self.last_bounds,rect,max(1,round(2*self.scale)))
                self.placement_context = context
                self.hidden_reason = None
                settled = self.position_overlay(rect)
        elif not self.drag:
            self.hidden_reason = "inactive"
            if self.motion.target:
                if self.motion.target_alpha != 0:self.record_visibility("fade_out","inactive")
                self.motion.retarget(self.motion.target,0,time.monotonic())
                settled = self.animate_frame()
        self.write_status()
        self.root.after(16 if not settled else 80 if show else 200,self.tick)

    def write_status(self):
        if self.args.status_file:
            state = {"pid": os.getpid(), "running": not self.stop.is_set(), "thread_id": self.args.thread_id, "overlay_hwnd": self.hwnd,
                     "target_hwnd": self.target["hwnd"] if self.target else None,
                     "bound_title": self.bound_title, "binding_mode": self.binding.mode,
                     "binding_status": self.binding.status, "binding_revision": self.binding.revision,
                     "binding_source": "main_document_title" if self.binding.mode == "auto" else "manual",
                     "last_context_probe": self.anchor_at,
                     "visible": self.visible, "placement": self.placement_mode,
                     "hidden_reason": self.hidden_reason, "app_popup_open": self.interaction_open,
                     "topmost": bool(self.win.get_long(self.hwnd,-20) & 0x8),
                     "owner_hwnd": self.win.get_long(self.hwnd,-8),
                     "version": VERSION, "locked": self.locked, "mouse_passthrough": self.passthrough,
                     "position_updates": self.position_updates, "opacity": self.opacity,
                     "display_mode": self.display_mode, "compact":self.compact, "animations":self.animations,
                     "material": "native_blur" if hasattr(self,"surface") and self.surface.material.available else "translucent",
                     "material_fallback":self.surface.material.reason if hasattr(self,"surface") else None,
                     "blur_visible":self.surface.material.visible if hasattr(self,"surface") else False,
                     "blur_hides":self.surface.material.hides if hasattr(self,"surface") else 0,
                     "foreground_uploads":getattr(getattr(self,"surface",None),"uploads",0),
                     "foreground_refreshes":getattr(getattr(self,"surface",None),"repairs",0),
                     "foreground_paint_guard":bool(getattr(getattr(getattr(self,"surface",None),"paint_guard",None),"handles",None)),
                     "foreground_paint_fallback":getattr(getattr(getattr(self,"surface",None),"paint_guard",None),"reason",None),
                     "foreground_tk_paints_suppressed":getattr(getattr(getattr(self,"surface",None),"paint_guard",None),"suppressed",0),
                     "presentation_error":getattr(getattr(self,"surface",None),"last_error",None),
                     "theme_color":getattr(self,"theme_color",theme.DEFAULT),
                     "settings_open":bool(getattr(self,"settings_panel",None)),
                     "settings_tab":getattr(getattr(self,"settings_panel",None),"tab",None),
                     "expanded_mode":getattr(self,"expanded_mode",self.display_mode),
                     "visibility_events":getattr(self,"visibility_events",[]),
                     "selected_metrics": list(self.visible_metrics), "snapshot_from_cache": bool(self.snapshot and self.snapshot.get("from_cache")),
                     "probe_pid": self.probe.process.pid if self.probe.process and self.probe.process.poll() is None else None,
                     "probe_starts": self.probe.starts, "probe_requests": self.probe.requests,
                     "probe_latency_ms": self.probe.last_latency_ms,
                     "bounds": self.last_bounds.__dict__ if self.last_bounds else None,
                     "composer_bounds": self.composer.__dict__ if self.composer else None,
                     "metrics_available": bool(self.snapshot and self.snapshot.get("available")),
                     "native_visible": bool(self.win.user32.IsWindowVisible(self.hwnd)),
                     "canvas_visible": bool(self.win.user32.IsWindowVisible(self.canvas.winfo_id())),
                     "font_size": self.font_size, "font_family": ui_font_family(),
                     "render_style": "segmented", "render_error": self.render_error,
                     "image_size": list(self.surface.size) if hasattr(self,"surface") and self.surface.size else
                                   [self.image.width(), self.image.height()] if self.image else None,
                     "displayed_metrics": [cell["key"] for cell in self.layout],
                     "settings_saved": not self.settings_error,
                     "no_activate": bool(self.win.get_long(self.hwnd,-20) & 0x08000000)}
            data = json.dumps(state, ensure_ascii=False)
            semantic = (state["running"], self.visible, self.hidden_reason, self.args.thread_id,
                        self.binding.revision, self.interaction_open, self.locked, self.passthrough,
                        self.visible_metrics, state["snapshot_from_cache"])
            now = time.monotonic()
            if semantic == getattr(self, "status_semantic", None) and now-getattr(self, "status_at", 0) < 1:
                return
            if data != getattr(self, "last_status", None) or (getattr(self, "runtime", None) and now-getattr(self,"status_at",0) >= 1):
                try:
                    if getattr(self, "runtime", None):
                        self.runtime.write(state)
                    else:
                        atomic_json(self.args.status_file, state)
                except OSError:
                    self.status_error = True
                    return
                self.last_status = data
                self.status_semantic, self.status_at = semantic, now

    def drag_start(self, event):
        if self.passthrough:
            return
        width = self.last_bounds.width if self.last_bounds else self.canvas.winfo_width()
        height = self.last_bounds.height if self.last_bounds else self.height
        control = style.control_at(event.x, event.y, width, height,
                                   self.scale*self.font_size/15)
        if control == "menu":
            self.context_menu(event)
            return
        if self.locked and control != "drag" and not self.win.edit_modifier_down() and not (self.display_mode == "desktop" and self.compact):
            return
        if self.last_bounds:
            self.drag = (event.x_root-self.last_bounds.left, event.y_root-self.last_bounds.top)
            self.drag_origin = (event.x_root,event.y_root)
            self.drag_moved = False
            self.drag_control = control

    def drag_move(self, event):
        if self.drag and self.last_bounds:
            dx,dy = event.x_root-self.drag_origin[0],event.y_root-self.drag_origin[1]
            threshold = max(4,round(5*self.scale))
            self.drag_moved = self.drag_moved or dx*dx+dy*dy > threshold*threshold
            if not self.drag_moved:
                return
            x,y = event.x_root-self.drag[0],event.y_root-self.drag[1]
            rect = Rect(x,y,x+self.last_bounds.width,y+self.last_bounds.height)
            self.last_bounds = rect
            if hasattr(self,"surface"):
                self.surface.present(rect,255)
            else:
                self.win.show_without_focus(self.hwnd, rect)
            self.motion.retarget(rect,255,time.monotonic(),immediate=True)
            self.applied_bounds = rect
            self.position_updates += 1

    def drag_end(self, event):
        if self.drag and event is not None:
            self.drag_move(event)  # The final motion event may have been coalesced.
        if self.drag and not self.drag_moved and getattr(self,"drag_control",None) == "drag":
            self.drag = None
            self.toggle_capsule()
            self.refresh_input_mode(True)
            return
        if self.drag and self.display_mode == "desktop":
            if self.drag_moved:
                area = self.win.work_area(self.hwnd)
                if area:
                    self.desktop_position = remember(area,self.last_bounds,self.scale)
                    self.save_preferences()
            elif self.compact and getattr(self,"drag_control",None) != "drag":
                self.toggle_compact()
            self.drag = None
            self.refresh_input_mode(True)
            return
        if self.drag and self.drag_moved and self.target and self.last_bounds:
            window = self.win.client_rect(self.target["hwnd"])
            if window:
                composer = self.current_composer
                if composer and time.monotonic()-self.anchor_at<=4:
                    self.manual = remember(window,self.last_bounds,self.scale,composer)
                    self.manual["center_ratio"] = max(0,min(1,self.manual["center_ratio"]))
                else:
                    self.manual = remember(window,self.last_bounds,self.scale)
                self.save_preferences()
        self.drag = None
        self.refresh_input_mode(bool(self.target and self.win.active_target(self.target["hwnd"])))

    def context_menu(self, event, tab="strip"):
        if self.passthrough:
            return
        if self.settings_panel:
            self.settings_panel.window.lift()
            return
        from settings_panel import SettingsPanel
        self.menu_open = True
        self.refresh_input_mode(True)
        self.settings_panel = SettingsPanel(self, event.x_root, event.y_root, tab=tab)
        self.root.after_idle(self.refresh_surface)

    def refresh_surface(self):
        """Tk settings creation/destruction can invalidate an unchanged layered HWND."""
        if not self.stop.is_set() and self.visible and self.last_bounds and hasattr(self,"surface"):
            self.surface.invalidate()
            self.draw(self.last_bounds.width)
            self.surface.present(self.last_bounds,self.opacity)

    def open_settings(self):
        from types import SimpleNamespace
        area = self.win.work_area(self.target["hwnd"] if self.target else self.hwnd)
        self.menu_open = True
        self.refresh_input_mode(True)
        self.context_menu(SimpleNamespace(x_root=area.right-24,y_root=area.bottom-24),
                          tab=getattr(self.args,"settings_tab","strip"))

    def select_thread(self, identity, title):
        self.apply_binding(self.binding.pin(identity,title))

    def binding_label(self):
        return "跟随当前：" if self.binding.mode == "auto" else "固定统计："

    def toggle_follow(self):
        if bool(self.follow_choice.get()) == (self.binding.mode == "auto"):
            return
        if self.follow_choice.get():
            self.apply_binding(self.binding.automatic())
        else:
            self.apply_binding(self.binding.manual())

    def apply_binding(self, binding):
        if binding == self.binding:
            return
        if self.binding.identity and self.snapshot and not self.snapshot.get("from_cache"):
            self.cache.put(self.binding.identity, self.snapshot)
        self.binding = binding
        self.args.thread_id, self.bound_title = binding.identity,binding.title
        self.thread_choice.set(binding.identity or "")
        self.follow_choice.set(binding.mode == "auto")
        # Identity has just been verified by exact unique title matching or an
        # explicit manual choice. Never restore by title, recency or resemblance.
        self.snapshot = self.cache.restore(binding.identity)
        self.metrics_wake.set()
        self.update_freshness()
        self.root.title("Codex Pulse — "+(binding.identity or "等待识别")[:8])
        if self.last_bounds:
            self.draw(self.last_bounds.width)

    def apply_snapshot(self, identity, snapshot, revision):
        if not self.binding.accepts(identity,revision):
            return False
        if snapshot.get("thread_id") not in (None, identity):
            return False
        self.snapshot = snapshot
        if snapshot.get("available"):
            self.cache.put(identity, snapshot)
        else:
            self.cache.entries.pop(identity, None)
        self.update_freshness()
        return True

    def update_freshness(self):
        panel = getattr(self, "settings_panel", None)
        if panel:
            panel.refresh()

    def reset_position(self):
        self.manual = None
        self.placement_context = None
        self.save_preferences()

    def close(self, reason="user_closed"):
        if self.stop.is_set():
            return
        self.stop.set()
        if getattr(self, "runtime", None):
            self.runtime.reason = self.runtime.reason or reason
        self.metrics_wake.set()
        if getattr(self, "settings_panel", None):
            self.settings_panel.close()
        self.win.hide(self.hwnd)
        if hasattr(self,"surface"):
            self.surface.close()
        self.visible = False
        self.write_status()
        self.probe.close()
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def run(self):
        print("Codex Pulse floating strip started in " + self.binding.mode + " mode",flush=True)
        self.root.mainloop()


def main():
    if sys.platform != "win32":
        raise SystemExit("The floating strip currently supports Windows only.")
    import native_windows as win
    win.dpi_awareness()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-id",default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--fixed",action="store_true",help="Keep explicitly selected chat statistics instead of following the visible chat")
    parser.add_argument("--codex-home",type=Path,default=Path(os.environ.get("CODEX_HOME",Path.home()/".codex")))
    parser.add_argument("--target-hwnd",type=int)
    parser.add_argument("--status-file",type=Path,default=preferences.default_path().with_name("runtime.json"))
    parser.add_argument("--settings-file",type=Path,default=preferences.default_path())
    parser.add_argument("--legacy-position-file",type=Path,help="Migrate a previous version's position on first launch")
    parser.add_argument("--duration",type=float,help="Optional local smoke-test duration in seconds")
    parser.add_argument("--run-id",help=argparse.SUPPRESS)
    parser.add_argument("--preview",action="store_true",help="Bounded smoke test: show even when the target app is inactive")
    parser.add_argument("--diagnose",action="store_true")
    parser.add_argument("--open-settings",action="store_true",help="Open the native settings panel after launch")
    parser.add_argument("--settings-tab",choices=("strip","display","session"),default="strip",
                        help="Initial page when opening settings at launch")
    parser.add_argument("--edit",action="store_true",help="Start unlocked for position and metric configuration")
    args = parser.parse_args()
    if args.preview and (not args.duration or not 0 < args.duration <= 10):
        parser.error("--preview requires --duration between 0 and 10 seconds.")
    if args.diagnose:
        windows = win.app_windows()
        catalog = thread_catalog.recent(args.codex_home.resolve(),limit=None,include_archived=True)
        for window in windows:
            anchor,title,status,interaction = find_context(window["hwnd"])
            window["composer_bounds"] = anchor.__dict__ if anchor else None
            binding = Binding().follow(title,catalog,status)
            window["current_chat"] = {"id":binding.identity,"title":binding.title,"status":binding.status}
            window["app_popup_open"] = interaction
        print(json.dumps(windows,ensure_ascii=False,indent=2))
        return
    if args.fixed and not args.thread_id:
        parser.error("Fixed mode requires --thread-id.")
    if args.thread_id and not re.fullmatch(r"[0-9a-fA-F-]{36}",args.thread_id):
        parser.error("Provide a valid Codex thread UUID with --thread-id.")
    # A named local mutex avoids stacked strips when a new chat invokes the plugin.
    win.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
    win.kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = win.kernel32.CreateMutexW(None,False,"Local\\CodexPulseFloatingStrip")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        win.kernel32.CloseHandle(mutex)
        print("Codex Pulse is already running. Its right-click menu controls automatic following or fixed statistics.")
        return
    from tk_lifetime import TkLifetime
    lifetime = TkLifetime()
    args.runtime = RuntimeSession(args.status_file, VERSION, args.run_id)
    app = None
    try:
        args.runtime.write({"running": True, "visible": False, "native_visible": False})
        app = Overlay(args)
        lifetime.attach(app.root)
        app.run()
        if args.runtime.error:
            raise SystemExit(1)
    except Exception as exception:
        args.runtime.fail(exception)
        raise
    finally:
        try:
            if app is not None:
                app.close()
                deadline = time.monotonic() + 6
                for worker in app.workers:
                    worker.join(max(0, deadline-time.monotonic()))
            args.runtime.finish()
        finally:
            app = None
            lifetime.stop()
            win.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
