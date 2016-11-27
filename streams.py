import gi
gi.require_version('Gst', '1.0')
gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk, Gst, Gdk, GLib

from sys import argv, exit

from xml.etree import ElementTree as Et

from os import path, makedirs, remove

from subprocess import Popen, PIPE, DEVNULL

from collections import OrderedDict

import random

import json

import threading

import socket

from export import Export
from station import Station, RE_URL

GLADE_LOC = "{}/streams.glade".format(path.dirname(__file__))


class MainWindow:
    def __init__(self):
        self.edit = False

        self.builder = Gtk.Builder()
        self.builder.add_from_file(GLADE_LOC)

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

        self.bookmarks = self.builder.get_object("bookmarks")

        self.treeview = self.builder.get_object("view_bookmarks")
        self.treeview.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK,
                                               [("text/plain", Gtk.TargetFlags.SAME_WIDGET, 0)],
                                               Gdk.DragAction.MOVE)
        self.treeview.enable_model_drag_dest([("text/plain", Gtk.TargetFlags.SAME_WIDGET, 0)],
                                             Gdk.DragAction.MOVE)

        self.selection = self.builder.get_object("bookmarks_view_selection")

        self.list_commands = OrderedDict()

        self.commands_list_load()
        self.command_menu_update()

        threading.Thread(target=self.ipc, daemon=True).start()

        self.load_db()

        self.restore_state()

        self.window.show_all()

        if len(argv) > 1:
            if RE_URL.match(argv[1]):
                self.create_station(argv[1])
            else:
                self.add_from_file(argv[1])

    def ipc(self):
        ipc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port = 10101
        bound = False
        while not bound:
            port = random.randint(10000, 60000)
            try:
                ipc_socket.bind(("localhost", port))
            except socket.error as err:
                pass
            else:

                bound = True

        file_path = path.expanduser("~/.cache/streams_port")
        if not path.exists(path.dirname(file_path)):
            makedirs(path.dirname(file_path))
        ipc_file = open(file_path, "w")
        ipc_file.write(str(port))
        ipc_file.close()

        ipc_socket.listen(5)
        while True:
            conn, addr = ipc_socket.accept()
            dat = conn.recv(1024).decode()
            self.window.present()
            if RE_URL.match(dat):
                GLib.idle_add(self.create_station, dat)
            elif path.isfile(dat):
                GLib.idle_add(self.add_from_file, dat)
            else:
                print("No URL or file to open")

    def load_db(self):
        db_path = path.expanduser("~/.config/streams/stations.xml")
        if not path.isfile(db_path):
            return

        db = Et.parse(db_path)
        root = db.getroot()

        for server in root.iter("server"):
            row = list()
            row.append(server.text)
            row.append(server.get("url"))
            row.append(server.get("genres"))
            row.append(server.get("web"))
            row.append(server.get("codec"))
            row.append(int(server.get("bitrate")))
            row.append(int(server.get("sample")))

            is_server = server.get("folder") == "True"
            row.append(is_server)

            if is_server:
                weight = 700
            else:
                weight = 400

            row.append(weight)

            parent_path = server.get("parent")
            if parent_path == "":
                parent = None
            else:
                parent = self.bookmarks.get_iter(parent_path)

            self.bookmarks.append(parent, row)

        return

    def on_selection_change(self, selection):
        self.edit_mode(False)
        self.load_selection_data()
        return

    def on_activation(self, text, path, column):
        if self.bookmarks[path][7]:
            return

        url = self.bookmarks[path][1]
        cmd = text.get_text().format(url)
        cmd = cmd.split(" ", 1)
        try:
            Popen([cmd[0], cmd[1]],
                  shell=False,
                  stdout=PIPE,
                  stderr=DEVNULL)
        except FileNotFoundError as err:
            self.error_popup(err)

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
            self.error_popup("Invalid URL")

        return

    def add_file(self, widget=None):
        dial = Gtk.FileChooserDialog("Choose file to open",
                                     self.window,
                                     Gtk.FileChooserAction.OPEN,
                                     (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                      Gtk.STOCK_OPEN, Gtk.ResponseType.OK
                                      ))

        filter = Gtk.FileFilter()
        filter.set_name("Playlists")
        filter.add_pattern("*.pls")
        filter.add_pattern("*.m3u")
        filter.add_pattern("*.xspf")
        dial.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name("All")
        filter.add_pattern("*")
        dial.add_filter(filter)

        response = dial.run()
        file = dial.get_filename()
        ext = dial.get_filter().get_name()

        dial.destroy()

        if response == Gtk.ResponseType.OK:
            self.add_from_file(file)

    def add_from_file(self, location):
        Station(self, location, self.bookmarks, None, True)
        self.save_db()
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
            row = [fol_name, "", "", "", "", 0, 0, True, 700]
            self.bookmarks.append(None, row)
            self.save_db()

        return

    def create_station(self, url, parent=None):
        Station(self, url, self.bookmarks, parent)
        self.save_db()
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
        self.bookmarks.remove(row)

        self.save_db()
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

        self.bookmarks.set_value(row, 0, name)
        self.bookmarks.set_value(row, 1, url)
        self.bookmarks.set_value(row, 2, genres)
        self.bookmarks.set_value(row, 3, web)
        self.bookmarks.set_value(row, 4, codec)
        self.bookmarks.set_value(row, 5, int(bitrate))
        self.bookmarks.set_value(row, 6, int(sample))

        self.save_db()

        self.edit_mode(False)

        return

    def on_cancel(self, button):
        self.edit_mode(False)
        self.load_selection_data()
        return

    def on_dig(self, text):
        url = text.get_text()
        new_url = Station.dig(self.window, url, False)
        if new_url == "error":
            self.error_popup("An error happened")
            return

        if type(new_url) is str:
            text.set_text(new_url)

        elif type(new_url) is tuple:
            if len(new_url[1]) == 1:
                text.set_text(new_url[1][0])
            else:
                if new_url[0] is not None:
                    par_row = [new_url[0], "", "", "", "", 0, 0, True, 700]
                    parent = self.bookmarks.append(None, par_row)
                else:
                    parent = None

                for url in new_url[1]:
                    self.create_station(url, parent)

                self.edit_mode(False)
                self.load_selection_data()

                self.error_popup("Multiple stations added,\nsource station has not been changed")

        return

    def on_autofill(self, text):
        url = text.get_text()
        data = Station.fetch_infos(self, url)

        if data == "error":
            return

        self.builder.get_object("text_name").set_text(data[0])
        self.builder.get_object("text_url").set_text(data[1])
        self.builder.get_object("text_genres").set_text(data[2])
        self.builder.get_object("text_web").set_text(data[3])
        self.builder.get_object("text_codec").set_text(data[4])
        self.builder.get_object("text_bitrate").set_text(str(data[5]))
        self.builder.get_object("text_sample").set_text(str(data[6]))

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
            bitrate = 0
            sample = 0

        text_url.set_text(url)
        text_genres.set_text(genres)
        text_web.set_text(web)
        text_codec.set_text(codec)
        text_bitrate.set_text(str(bitrate))
        text_sample.set_text(str(sample))

        return

    def add_row_to_db(self, model, path, iter, user_data):
        row = self.bookmarks.get(iter, 0, 1, 2, 3, 4, 5, 6, 7)
        server = Et.SubElement(user_data, "server")
        server.text = row[0]
        server.set("url", row[1])
        server.set("genres", row[2])
        server.set("web", row[3])
        server.set("codec", row[4])
        server.set("bitrate", str(row[5]))
        server.set("sample", str(row[6]))
        server.set("folder", str(row[7]))

        parent_iter = self.bookmarks.iter_parent(iter)
        if parent_iter is not None:
            parent = self.bookmarks.get_path(parent_iter)
        else:
            parent = ""
        server.set("parent", parent)

    def save_db(self, db=None, a=None, b=None):
        print("Saving DB")

        stations = Et.Element("stations")

        self.bookmarks.foreach(self.add_row_to_db, stations)

        db = Et.ElementTree(stations)
        db_path = path.expanduser("~/.config/streams/stations.xml")

        if not path.exists(path.dirname(db_path)):
            makedirs(path.dirname(db_path))

        db.write(db_path)
        return

    def exit(self, a, b):
        self.write_state()

        ipc_file = path.expanduser("~/.cache/streams_port")
        remove(ipc_file)

        Gtk.main_quit()
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

        self.error_popup("Command doesn't match any saved command")
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

    def error_popup(self, err):
        dialog = Gtk.MessageDialog(self.window,
                                   (Gtk.DialogFlags.MODAL|Gtk.DialogFlags.DESTROY_WITH_PARENT),
                                   Gtk.MessageType.ERROR,
                                   Gtk.ButtonsType.CLOSE,
                                   err)
        dialog.set_default_response(Gtk.ResponseType.CLOSE)
        dialog.run()
        dialog.destroy()
        return

    def drag_data_received(self, treeview, context, x, y, selection, info, etime):
        selec = treeview.get_selection()
        row, cursor = selec.get_selected()
        data = []
        for d in row[cursor]:
            data.append(d)

        drop_info = treeview.get_dest_row_at_pos(x, y)

        if drop_info:
            source_folder = data[7]
            pat, position = drop_info
            dest_iter = self.bookmarks.get_iter(pat)
            dest_folder = self.bookmarks.get_value(dest_iter, 7)
            dest_parent = self.bookmarks.iter_parent(dest_iter)
            if not source_folder:
                if position == Gtk.TreeViewDropPosition.BEFORE:
                    new_iter = self.bookmarks.insert_before(dest_parent, dest_iter, data)
                elif position == Gtk.TreeViewDropPosition.AFTER:
                    new_iter = self.bookmarks.insert_after(dest_parent, dest_iter, data)
                elif dest_folder:
                    new_iter = self.bookmarks.append(dest_iter, data)
                else:
                    new_iter = self.bookmarks.insert_before(dest_parent, dest_iter, data)
            else:
                if dest_parent is not None:
                    new_iter = self.bookmarks.insert_before(None, dest_parent, data)
                elif position == Gtk.TreeViewDropPosition.BEFORE:
                    new_iter = self.bookmarks.insert_before(None, dest_iter, data)
                elif position == Gtk.TreeViewDropPosition.AFTER:
                    new_iter = self.bookmarks.insert_after(None, dest_iter, data)
                else:
                    new_iter = self.bookmarks.insert_before(None, dest_iter, data)
        else:
            new_iter = self.bookmarks.append(None, data)

        for it in row[cursor].iterchildren():
            dat = []
            for value in it:
                dat.append(value)
            self.bookmarks.append(new_iter, dat)

        context.finish(True, True, etime)

        self.save_db()
        return

    def on_export(self, menu_item):
        dial = Gtk.FileChooserDialog("Choose destination file",
                                     self.window,
                                     Gtk.FileChooserAction.SAVE,
                                     (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                      Gtk.STOCK_SAVE, Gtk.ResponseType.OK
                                      ))

        filter = Gtk.FileFilter()
        filter.set_name("pls")
        filter.add_pattern("*.pls")
        dial.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name("m3u")
        filter.add_pattern("*.m3u")
        dial.add_filter(filter)

        response = dial.run()
        file = dial.get_filename()
        ext = dial.get_filter().get_name()

        dial.destroy()

        if response == Gtk.ResponseType.OK:
            self.do_export(file, ext)

        return

    def do_export(self, file, ext):
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

        exp = Export(file, self.bookmarks)

        f = open(file, "w")
        f.write(exp.data)
        f.close()

        return


if __name__ == '__main__':
    ipc_path = path.expanduser("~/.cache/streams_port")
    if path.isfile(ipc_path):
        f = open(ipc_path, "r")
        ipc_port = int(f.read())
        f.close()

        if len(argv) > 1:
            d = argv[1]
        else:
            d = ""

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("localhost", ipc_port))
        except socket.error as e:
            s.close()
            pass
        else:
            s.send(d.encode())
            s.close()
            exit(0)

    GObject.threads_init()
    Gst.init(None)
    MainWindow()
    Gtk.main()
