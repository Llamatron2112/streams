import gi
gi.require_version('Gst', '1.0')
gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gio, Gtk, Gst

import sys

from mainwindow import MainWindow


class Streams(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.llamatron.streams",
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.register()
        self.connect("activate", self.show_window)
        self.connect("open", self.open_files)

    def show_window(self, *args):
        if not hasattr(self, "window"):
            self.window = MainWindow(self)
        else:
            self.window.window.present()

    def open_files(self, app, files, hint, *args):
        if not hasattr(self, "window"):
            self.show_window()
        self.window.open(files)

if __name__ == '__main__':
    GObject.threads_init()
    Gst.init(None)
    app = Streams()
    exit_status = app.run(sys.argv)
    sys.exit(exit_status)
