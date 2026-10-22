"""Collect Tk reference cycles only on the interpreter's owning thread."""
import gc
import threading


class TkLifetime:
    def __init__(self):
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Tk lifetime must belong to the main thread")
        self.was_enabled = gc.isenabled()
        self.root = None
        self.job = None
        gc.disable()

    def attach(self, root):
        self.root = root
        self.job = root.after(750, self.collect)

    def collect(self):
        # Tk widgets, variables and images can form cycles after a panel closes.
        # Automatic cyclic GC can otherwise finalize their Tcl interpreter in a
        # metric/probe thread. Refcounting is unaffected by gc.disable().
        gc.collect()
        if self.root is not None:
            self.job = self.root.after(750, self.collect)

    def stop(self):
        if self.root is not None and self.job:
            try:
                self.root.after_cancel(self.job)
            except Exception:
                pass
        self.root, self.job = None, None
        gc.collect()
        if self.was_enabled:
            gc.enable()
