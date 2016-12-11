import gi
gi.require_version('Gst', '1.0')
gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gio, Gtk, Gst, Gdk, GLib

import sys

from os import path, makedirs, remove

import traceback

from subprocess import Popen, PIPE, DEVNULL

from collections import OrderedDict

import json

from station import Station
from constants import RE_URL
from tools import get_metadata, get_next_url
from drag import drag
from db import DataBase


class Streams(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.llamatron.streams",
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.register()
        self.connect("activate", self.show_window)
        self.connect("open", self.open_files)

    def show_window(self, *args):
        if len(self.get_windows()) == 0:
            self.window = MainWindow(self)
        else:
            self.window.window.present()

    def open_files(self, app, files, hint, *args):
        if len(self.get_windows()) == 0:
            self.show_window()
        self.window.open(files)


class MainWindow:
    def __init__(self, application):
        self.application = application
        self.edit = False
        self.locked = True
        self.builder = Gtk.Builder()
        glade_path = "{}/streams.glade".format(path.dirname(__file__))
        self.builder.add_from_file(glade_path)

        self.window = self.builder.get_object("main_win")
        self.window.set_wmclass("Streams", "Streams")
        self.window.set_title("Streams")
        self.window.connect("delete-event", self.exit)

        events = {
            "on_selection_change": self.on_selection_change,
            "on_activation": self.on_activation,
            "on_add_clicked": self.on_add_clicked,
            "on_edit_clicked": self.on_edit,
            "on_delete_clicked": self.on_delete,
            "on_save_clicked": self.on_save,
            "on_cancel_clicked": self.on_cancel,
            "on_dig_clicked": self.on_dig,
            "on_auto_clicked": self.on_autofill,
            "on_url_change": self.dig_button_state,
            "on_web_change": self.web_button_state,
            "on_web_clicked": self.visit_web,
            "on_menuchoice_save_activate": self.command_save,
            "on_menuchoice_delete_activate": self.command_delete,
            "on_command_menu_activated": self.command_menu_activated,
            "on_drag_data_received": self.drag_data_received,
            "on_menu_item_export_activate": self.on_export,
            "on_menu_item_addurl_activate": self.add_url,
            "on_menu_item_addfold_activate": self.add_folder,
            "on_menu_item_openfile_activate": self.add_file
        }
        self.builder.connect_signals(events)

        self.db = DataBase(str, str, str, str, str, str, str, bool, int)
        self.db.load()

        self.treeview = self.builder.get_object("view_bookmarks")
        self.treeview.set_model(self.db)
        self.treeview.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK,
                                               [("list_row", Gtk.TargetFlags.SAME_WIDGET, 0)],
                                               Gdk.DragAction.MOVE)
        self.treeview.enable_model_drag_dest([("list_row", Gtk.TargetFlags.SAME_WIDGET, 0)],
                                             Gdk.DragAction.MOVE)

        self.selection = self.builder.get_object("bookmarks_view_selection")

        self.list_commands = OrderedDict()

        self.commands_list_load()
        self.command_menu_update()

        self.restore_state()

        self.window.set_application(application)
        self.window.show_all()
        self.locked = False

    def open(self, files):
        for f in files:
            uri = f.get_uri()
            print(uri)
            if RE_URL.match(uri) and str.lower(uri[0:3]) == "http":
                self.create_station(uri)
            else:
                self.add_from_file(uri[6:])

    def on_selection_change(self, selection):
        self.edit_mode(False)
        self.load_selection_data()
        return

    def on_activation(self, text, path, column):
        if self.db[path][7]:
            return

        url = self.db[path][1]
        cmd = text.get_text().format(url)
        cmd = cmd.split(" ", 1)
        try:
            Popen([cmd[0], cmd[1]],
                  shell=False,
                  stdout=PIPE,
                  stderr=DEVNULL)
        except Exception as err:
            traceback.print_exc()
            self.popup(err)

        return

    def on_add_clicked(self, button):
        choice_dial = Gtk.MessageDialog(self.window,
                                        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                        Gtk.MessageType.QUESTION,
                                        ("Station", 1, "Folder", 2),
                                        "Do you want to add a station or a folder ?")
        choice_dial.set_default_response(1)
        choice = choice_dial.run()

        choice_dial.destroy()

        if choice == 1:
            self.add_url()

        elif choice == 2:
            self.add_folder()

        return

    def add_url(self, widget=None):
        dialog = Gtk.MessageDialog(self.window,
                                   Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.OK_CANCEL,
                                   "Enter the new station's URL"
                                   )
        text_new_url = Gtk.Entry(input_purpose=Gtk.InputPurpose.URL)
        text_new_url.set_activates_default(Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.add(text_new_url)
        text_new_url.show()

        new_url = ""
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            new_url = text_new_url.get_text()

        dialog.destroy()

        if RE_URL.match(new_url):
            self.create_station(new_url)
        else:
            self.popup("Invalid URL")

        return

    def add_file(self, widget=None):
        dial = Gtk.FileChooserDialog("Choose file to open",
                                     self.window,
                                     Gtk.FileChooserAction.OPEN,
                                     (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                      Gtk.STOCK_OPEN, Gtk.ResponseType.OK
                                      ))

        filt = Gtk.FileFilter()
        filt.set_name("Playlists")
        filt.add_pattern("*.pls")
        filt.add_pattern("*.m3u")
        filt.add_pattern("*.xspf")
        dial.add_filter(filt)

        filt = Gtk.FileFilter()
        filt.set_name("All")
        filt.add_pattern("*")
        dial.add_filter(filt)

        response = dial.run()
        file = dial.get_filename()

        dial.destroy()

        if response == Gtk.ResponseType.OK:
            self.add_from_file(file)

    def add_from_file(self, location):
        if self.locked:
            print("Locked")
            return
        self.locked = True

        win_wait = self.pls_wait()
        while Gtk.events_pending():
            Gtk.main_iteration()

        try:
            Station(self, location, None, True)
        except Exception as err:
            traceback.print_exc()
            win_wait.destroy()
            self.popup(err)
            self.locked = False
        else:
            win_wait.destroy()
            self.db.save()
            self.locked = False
        return

    def add_folder(self, widget=None):
        dialog = Gtk.MessageDialog(self.window,
                                   Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.OK_CANCEL,
                                   "Enter the new folder's name"
                                   )
        text_fold = Gtk.Entry()
        text_fold.set_activates_default(Gtk.ResponseType.OK)
        text_fold.show()
        area = dialog.get_content_area()
        area.add(text_fold)

        fol_name = ""

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            fol_name = text_fold.get_text()

        dialog.destroy()

        if fol_name != "":
            self.db.add_folder(fol_name)
            self.db.save()

        return

    def create_station(self, url, parent=None):
        if self.locked:
            print("Locked")
            return
        self.locked = True
        win_wait = self.pls_wait()
        while Gtk.events_pending():
            Gtk.main_iteration()

        try:
            Station(self, url, parent)
        except Exception as err:
            traceback.print_exc()
            win_wait.destroy()
            self.popup(err)
            self.locked = False
        else:
            self.db.save()
            win_wait.destroy()
            self.locked = False

        return

    def on_edit(self, button):
        self.edit_mode(True)
        return

    def on_delete(self, text):
        name = text.get_text()
        dialog = Gtk.MessageDialog(self.window,
                                   Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.OK_CANCEL,
                                   "Delete {} ?".format(name))
        dialog.set_default_response(Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            return

        row = self.selection.get_selected()[1]
        self.db.remove(row)

        self.db.save()
        return

    def on_save(self, button):
        row = self.selection.get_selected()[1]

        if row is None:
            return

        name = self.builder.get_object("text_name").get_text()
        url = self.builder.get_object("text_url").get_text()
        genres = self.builder.get_object("text_genres").get_text()
        web = self.builder.get_object("text_web").get_text()
        codec = self.builder.get_object("text_codec").get_text()
        bitrate = self.builder.get_object("text_bitrate").get_text()
        sample = self.builder.get_object("text_sample").get_text()

        if name == "":
            name = url

        self.db.set_value(row, 0, name)
        self.db.set_value(row, 1, url)
        self.db.set_value(row, 2, genres)
        self.db.set_value(row, 3, web)
        self.db.set_value(row, 4, codec)
        self.db.set_value(row, 5, bitrate)
        self.db.set_value(row, 6, sample)

        self.db.save()

        self.edit_mode(False)

        return

    def on_cancel(self, button):
        self.edit_mode(False)
        self.load_selection_data()
        return

    def on_dig(self, text):
        url = text.get_text()
        try:
            new_url = get_next_url(self, url)
        except Exception as err:
            traceback.print_exc()
            self.popup(err)
            return

        if type(new_url) is str:
            text.set_text(new_url)

        elif type(new_url) is tuple:
            if len(new_url[1]) == 1:
                text.set_text(new_url[1][0])
            else:
                if new_url[0] is not None:
                    parent = self.db.add_folder(new_url[0])
                else:
                    parent = None

                for url in new_url[1]:
                    self.create_station(url, parent)

                self.edit_mode(False)
                self.load_selection_data()

                self.popup("Multiple stations added,\nsource station has not been changed")

        return

    def on_autofill(self, text):
        url = text.get_text()
        try:
            data = get_metadata(url)
        except Exception as err:
            traceback.print_exc()
            self.popup(err)
        else:
            self.builder.get_object("text_name").set_text(data[0])
            self.builder.get_object("text_url").set_text(url)
            self.builder.get_object("text_genres").set_text(data[2])
            self.builder.get_object("text_web").set_text(data[3])
            self.builder.get_object("text_codec").set_text(data[4])
            self.builder.get_object("text_bitrate").set_text(data[5])
            self.builder.get_object("text_sample").set_text(data[6])

        return

    def edit_mode(self, state):
        self.edit = state

        row, cursor = self.selection.get_selected()
        button_auto = self.builder.get_object("button_auto")
        button_auto.set_sensitive(not row[cursor][7])

        self.builder.get_object("box_edit").set_visible(state)
        self.builder.get_object("box_actions").set_visible(not state)

        self.builder.get_object("text_name").set_editable(state)
        self.builder.get_object("text_url").set_editable(state)
        self.builder.get_object("text_genres").set_editable(state)
        self.builder.get_object("text_web").set_editable(state)
        self.builder.get_object("text_codec").set_editable(state)
        self.builder.get_object("text_bitrate").set_editable(state)
        self.builder.get_object("text_sample").set_editable(state)

        entry = self.builder.get_object("text_url")
        self.dig_button_state(entry)

        return

    def dig_button_state(self, entry):
        row, cursor = self.selection.get_selected()

        state = self.edit and not row[cursor][7]

        if state:
            self.builder.get_object("info_grid").child_set_property(entry, "width", 1)
        else:
            self.builder.get_object("info_grid").child_set_property(entry, "width", 2)

        self.builder.get_object("button_dig").set_visible(state)

        return

    def web_button_state(self, entry):
        url = entry.get_text()
        state = RE_URL.match(url)

        if state is None:
            state = False

        if state:
            self.builder.get_object("info_grid").child_set_property(entry, "width", 1)
        else:
            self.builder.get_object("info_grid").child_set_property(entry, "width", 2)
        self.builder.get_object("button_web").set_visible(state)

        return

    @staticmethod
    def visit_web(text):
        url = text.get_text()

        Popen(["xdg-open", url],
              shell=False,
              stdout=PIPE,
              stderr=DEVNULL)

        return

    def load_selection_data(self):
        row, cursor = self.selection.get_selected()
        if cursor is None:
            return

        text_name = self.builder.get_object("text_name")
        # text_label = self.builder.get_object("label_name")
        text_url = self.builder.get_object("text_url")
        label_url = self.builder.get_object("label_url")
        text_genres = self.builder.get_object("text_genres")
        label_genres = self.builder.get_object("label_genres")
        text_web = self.builder.get_object("text_web")
        label_web = self.builder.get_object("label_web")
        text_codec = self.builder.get_object("text_codec")
        label_codec = self.builder.get_object("label_codec")
        text_bitrate = self.builder.get_object("text_bitrate")
        label_bitrate = self.builder.get_object("label_bitrate")
        text_sample = self.builder.get_object("text_sample")
        label_sample = self.builder.get_object("label_sample")
        button_dig = self.builder.get_object("button_dig")
        button_web = self.builder.get_object("button_web")

        name = row[cursor][0]
        text_name.set_text(name)

        visible = not row[cursor][7]

        text_url.set_visible(visible)
        label_url.set_visible(visible)
        text_genres.set_visible(visible)
        label_genres.set_visible(visible)
        text_web.set_visible(visible)
        label_web.set_visible(visible)
        text_codec.set_visible(visible)
        label_codec.set_visible(visible)
        text_bitrate.set_visible(visible)
        label_bitrate.set_visible(visible)
        text_sample.set_visible(visible)
        label_sample.set_visible(visible)
        button_dig.set_visible(visible)
        button_web.set_visible(visible)

        if not row[cursor][7]:
            url = row[cursor][1]
            genres = row[cursor][2]
            web = row[cursor][3]
            codec = row[cursor][4]
            bitrate = row[cursor][5]
            sample = row[cursor][6]
        else:
            url = ""
            genres = ""
            web = ""
            codec = ""
            bitrate = ""
            sample = ""

        text_url.set_text(url)
        text_genres.set_text(genres)
        text_web.set_text(web)
        text_codec.set_text(codec)
        text_bitrate.set_text(bitrate)
        text_sample.set_text(sample)

        return

    def exit(self, a, b):
        self.write_state()

        ipc_file = path.expanduser("~/.cache/streams_port")
        remove(ipc_file)

        # Gtk.main_quit()
        return

    def write_state(self):
        x = self.window.get_size()[0]
        y = self.window.get_size()[1]
        pane = self.builder.get_object("panel").get_property("position")
        maximised = self.window.is_maximized()
        cmd = self.builder.get_object("text_command").get_text()

        cache_file = path.expanduser("~/.cache/streams/streams")

        if not path.exists(path.dirname(cache_file)):
            makedirs(path.dirname(cache_file))

        file = open(cache_file, 'w')
        file.write("{}\n".format(str(x)))
        file.write("{}\n".format(str(y)))
        file.write("{}\n".format(str(pane)))
        file.write("{}\n".format(str(maximised)))
        file.write("{}\n".format(str(cmd)))
        file.close()
        return

    def restore_state(self):
        cache_file = path.expanduser("~/.cache/streams/streams")

        if not path.exists(cache_file):
            return

        file = open(cache_file, 'r')

        x = int(file.readline())
        y = int(file.readline())
        pane = int(file.readline())
        maxi = file.readline()
        cmd = file.readline()

        file.close()

        self.window.resize(x, y)
        self.builder.get_object("panel").set_position(pane)

        if maxi == "True":
            self.window.maximize()

        self.builder.get_object("text_command").set_text(cmd[:-1])

        return

    def command_save(self, item):
        dialog = Gtk.MessageDialog(self.window,
                                   Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.OK_CANCEL,
                                   "Saving a new command line")
        area = dialog.get_content_area()
        dialog.format_secondary_text("Give a name for this action")
        text = Gtk.Entry()
        text.set_activates_default(Gtk.ResponseType.OK)
        area.add(text)
        text.show()
        dialog.set_default_response(Gtk.ResponseType.OK)
        response = dialog.run()

        name = text.get_text()
        dialog.destroy()

        if response != Gtk.ResponseType.OK:
            return

        cmd = self.builder.get_object("text_command").get_text()
        row = {name: cmd}

        if name in self.list_commands:
            dialog = Gtk.MessageDialog(self.window,
                                       Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                       Gtk.MessageType.QUESTION,
                                       Gtk.ButtonsType.OK_CANCEL,
                                       "A command with that name already exists")
            dialog.format_secondary_text("replace {}?".format(name))
            dialog.set_default_response(Gtk.ResponseType.OK)
            response = dialog.run()
            dialog.destroy()

            if response != Gtk.ResponseType.OK:
                return

        self.list_commands.update(row)
        self.command_menu_update()
        self.commands_list_save()
        return

    def command_delete(self, item):
        cmd = self.builder.get_object("text_command").get_text()

        for key in self.list_commands.keys():
            if self.list_commands[key] == cmd:
                dialog = Gtk.MessageDialog(self.window,
                                           Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                           Gtk.MessageType.QUESTION,
                                           Gtk.ButtonsType.OK_CANCEL,
                                           "You are about to delete an existing command")
                dialog.format_secondary_text("Do you really want to delete the {} command ?".format(key))
                dialog.set_default_response(Gtk.ResponseType.OK)
                response = dialog.run()
                dialog.destroy()

                if response != Gtk.ResponseType.OK:
                    return

                del self.list_commands[key]
                self.command_menu_update()
                self.commands_list_save()
                return

        self.popup("Command doesn't match any saved command")
        return

    def command_menu_activated(self, item):
        command = self.list_commands[item.get_label()]
        self.builder.get_object("text_command").set_text(command)
        return

    def command_menu_update(self):
        menu_command = self.builder.get_object("menu_window")

        for widget in menu_command.get_children():
            widget.destroy()

        button_save = Gtk.MenuItem.new_with_label("Save Command")
        button_save.connect("activate", self.command_save)
        button_save.show()

        button_delete = Gtk.MenuItem.new_with_label("Delete Command")
        button_delete.connect("activate", self.command_delete)
        button_delete.show()

        menu_separator = Gtk.SeparatorMenuItem()
        menu_separator.show()

        menu_command.append(button_save)
        menu_command.append(button_delete)
        menu_command.append(menu_separator)

        for key in self.list_commands.keys():
            choice = Gtk.MenuItem.new_with_label(key)
            choice.connect("activate", self.command_menu_activated)
            menu_command.append(choice)
            choice.show()

        return

    def commands_list_save(self):
        commands_file = path.expanduser("~/.config/streams/commands.json")

        if not path.exists(path.dirname(commands_file)):
            makedirs(path.dirname(commands_file))

        file = open(commands_file, 'w')
        json.dump(self.list_commands, file)
        file.close()
        return

    def commands_list_load(self):
        commands_file = path.expanduser("~/.config/streams/commands.json")

        if path.exists(commands_file):
            file = open(commands_file, 'r')
            self.list_commands = json.load(file, object_pairs_hook=OrderedDict)
            file.close()
        else:
            self.list_commands = {"Deadbeef": "deadbeef {}",
                                  "Rhythmbox": "rhythmbox {}"}

        return

    def popup(self, err, msg_type=Gtk.MessageType.ERROR):
        dialog = Gtk.MessageDialog(self.window,
                                   (Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT),
                                   msg_type,
                                   Gtk.ButtonsType.CLOSE,
                                   err)
        dialog.set_default_response(Gtk.ResponseType.CLOSE)
        dialog.run()
        dialog.destroy()
        return

    def pls_wait(self):
        win = Gtk.Window()
        win.set_default_size(100, 50)
        win.set_transient_for(self.window)
        win.set_modal(True)
        win.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        win.set_decorated(False)

        text = Gtk.Label("Please wait...")
        win.add(text)
        text.show()

        win.show_now()
        return win

    def drag_data_received(self, treeview, context, x, y, selection, info, etime):
        selec = treeview.get_selection()
        row, cursor = selec.get_selected()
        data = []
        for d in row[cursor]:
            data.append(d)

        drop_info = treeview.get_dest_row_at_pos(x, y)

        drag(data, drop_info, self.db, row, cursor)

        context.finish(True, True, etime)

        self.db.save()
        return

    def on_export(self, menu_item):
        dial = Gtk.FileChooserDialog("Choose destination file",
                                     self.window,
                                     Gtk.FileChooserAction.SAVE,
                                     (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                      Gtk.STOCK_SAVE, Gtk.ResponseType.OK
                                      ))

        filt = Gtk.FileFilter()
        filt.set_name("pls")
        filt.add_pattern("*.pls")
        dial.add_filter(filt)

        filt = Gtk.FileFilter()
        filt.set_name("m3u")
        filt.add_pattern("*.m3u")
        dial.add_filter(filt)

        response = dial.run()
        file = dial.get_filename()
        ext = dial.get_filter().get_name()

        dial.destroy()

        if response == Gtk.ResponseType.OK:
            file_ext = file.split(".")[-1]
            if file_ext.lower() != ext:
                file = "{}.{}".format(file, ext)

            if path.isfile(file):
                dial = Gtk.MessageDialog(self.window,
                                         Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                         Gtk.MessageType.QUESTION,
                                         Gtk.ButtonsType.OK_CANCEL,
                                         "{}\n\nFile already exists, overwrite ?".format(file)
                                         )
                response = dial.run()
                dial.destroy()
                if response != Gtk.ResponseType.OK:
                    return

            self.db.export(file)

        return


if __name__ == '__main__':
    # ipc_path = path.expanduser("~/.cache/streams_port")
    # if path.isfile(ipc_path):
    #     f = open(ipc_path, "r")
    #     ipc_port = int(f.read())
    #     f.close()
    #
    #     if len(argv) > 1:
    #         d = argv[1]
    #     else:
    #         d = ""
    #
    #     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     try:
    #         s.connect(("localhost", ipc_port))
    #     except socket.error as e:
    #         s.close()
    #         pass
    #     else:
    #         s.send(d.encode())
    #         s.close()
    #         exit(0)

    GObject.threads_init()
    Gst.init(None)
    app = Streams()
    exit_status = app.run(sys.argv)
    sys.exit(exit_status)
    # MainWindow()
    # Gtk.main()
