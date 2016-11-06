import gi
gi.require_version('Gst', '1.0')
gi.require_version("Gtk", "3.0")
gi.require_version('GstPbutils', '1.0')
from gi.repository import GObject, Gtk, Gst, GstPbutils

from sys import argv

import mimetypes

import urllib
from urllib import request, error

import http
from http.client import error

import re

from xml.etree import ElementTree as et

from os import path, makedirs

from subprocess import Popen, PIPE, DEVNULL

from collections import OrderedDict

import json

glade_loc = "{}/ui.glade".format(path.dirname(__file__))

url_regex = r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)"
re_url = re.compile(url_regex)

re_m3u_url = re_url
re_m3u_infos = re.compile(r"#EXTINF:-1,(.*)\n{}".format(url_regex))

re_pls_url = re.compile(r"File(\d+)={}".format(url_regex))
re_pls_title = re.compile(r"Title(\d+)=(.*)\n")

# re_xspf_url = re.compile(r"<location>{}</location>".format(url_regex))
# re_xspf_infos = re.compile(r"<track>")

pl_types = ["audio/x-scpls",
            "audio/mpegurl",
            "audio/x-mpegurl",
            "application/xspf+xml",
            "application/pls+xml",
            "application/octet-stream"]

audio_types = ["audio/mpeg",
               "application/ogg",
               "audio/ogg"
               "audio/aac",
               "audio/aacp"]

class MainWindow:
    def __init__(self):
        self.edit = False

        self.builder = Gtk.Builder()
        self.builder.add_from_file(glade_loc)

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
            "on_command_menu_activated": self.command_menu_activated
        }
        self.builder.connect_signals(events)

        self.bookmarks = self.builder.get_object("bookmarks")
        self.bookmarks.set_sort_column_id(0, Gtk.SortType.ASCENDING)

        self.treeview = self.builder.get_object("view_bookmarks")
        self.selection = self.builder.get_object("bookmarks_view_selection")

        self.list_commands = OrderedDict()

        self.commands_list_load()
        self.command_menu_update()

        self.load_db()

        self.restore_state()

        self.window.show_all()

        if len(argv) > 1:
            if re_url.match(argv[1]):
                self.add_station(argv[1])
            else:
                print("let's open", argv[1])
                self.add_from_file(argv[1])

    def load_db(self):
        db_path = path.expanduser("~/.config/streams/stations.xml")
        if not path.isfile(db_path):
            return

        db = et.parse(db_path)
        root = db.getroot()

        for server in root.iter("server"):
            row = []

            for value in server:
                data = value.text

                if data is None:
                    data = ""

                row.append(data)

            row[5] = int(row[5])
            row[6] = int(row[6])

            self.bookmarks.append(row)

        return

    def on_selection_change(self, selection):
        self.edit_mode(False)
        self.load_selection_data()
        return

    def on_activation(self, text, path, column):
        url = self.bookmarks[path][1]
        cmd = text.get_text().format(url)
        print(cmd)
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
        dialog = Gtk.MessageDialog(self.window,
                                   0,
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

        if response == -5:
            new_url = text_new_url.get_text()

        dialog.destroy()

        if new_url != "":
            self.add_station(new_url)

        return

    def add_station(self, url):
        print("Adding", url)
        content_type = None

        try:
            response = urllib.request.urlopen(url)
            info = response.info()
            content_type = info.get_content_type()
            print(content_type)

        except urllib.error.HTTPError as err:
            dialog = Gtk.MessageDialog(self.window,
                                       0,
                                       Gtk.MessageType.ERROR,
                                       Gtk.ButtonsType.CLOSE,
                                       err.code)
            dialog.format_secondary_text(err.reason)
            dialog.set_default_response(Gtk.ResponseType.CLOSE)
            dialog.run()
            dialog.destroy()
            return

        except http.client.BadStatusLine as err:
            if err.line == 'ICY 200 OK\r\n':
                self.add_url(url)
                return

        if content_type in pl_types:
            data = str(response.read(), "utf-8")
            response.close()
            print("Identified as playlist")
            self.add_playlist(url, data, content_type, "web")

        elif content_type in audio_types:
            response.close()
            print("Identified as audio")
            self.add_url(url)

        else:
            self.error_popup("Unknown content type: {}".format(content_type))

        return

    def add_url(self, url):
        infos = self.fetch_infos(url)
        print("Adding", url, "with", infos)
        new_row = self.bookmarks.append(infos)
        self.selection.select_iter(new_row)
        self.on_selection_change(self.selection)
        self.treeview.scroll_to_cell(self.selection.get_selected_rows()[1][0])
        self.save_db()
        return

    def on_edit(self, button):
        self.edit_mode(True)
        return

    def on_delete(self, text):
        name = text.get_text()
        dialog = Gtk.MessageDialog(self.window,
                                   0,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.OK_CANCEL,
                                   "Delete {} ?".format(name))
        dialog.set_default_response(Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()

        if response != -5:
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
        new_url = self.dig(url, True)
        if new_url != "error":
            text.set_text(new_url)

        return

    def on_autofill(self, text):
        url = text.get_text()
        data = self.fetch_infos(url)

        if data == "error":
            print("Error: Can't autofill")
            return

        self.builder.get_object("text_name").set_text(data[0])
        self.builder.get_object("text_url").set_text(data[1])
        self.builder.get_object("text_genres").set_text(data[2])
        self.builder.get_object("text_web").set_text(data[3])
        self.builder.get_object("text_codec").set_text(data[4])
        self.builder.get_object("text_bitrate").set_text(str(data[5]))
        self.builder.get_object("text_sample").set_text(str(data[6]))

        return

    def fetch_infos(self, url):
        server_url = self.dig(url, False)
        if server_url == "error":
            print("Error: Can't fetch infos")
            return "error"

        info = GstPbutils.Discoverer().discover_uri(server_url)

        name = ""
        genres = ""
        web = ""

        tags = info.get_tags()
        n = tags.n_tags() - 1
        for i in range(0, n):
            tag = tags.nth_tag_name(i)
            print(i, '=', tag, "=>", tags.get_string(tag)[1])
            if tag == "organization":
                name = tags.get_string(tag)[1]
            elif tag == "genre":
                genres = tags.get_string(tag)[1]
            elif tag == "location":
                web = tags.get_string(tag)[1]

        if name == "" or name is None:
            name = url

        stream_list = info.get_stream_list()
        audio_stream = stream_list[0]
        bitrate = int(audio_stream.get_bitrate() / 1000)
        sample = int(audio_stream.get_sample_rate())

        caps = audio_stream.get_caps()
        codec = GstPbutils.pb_utils_get_codec_description(caps)

        data = [name, url, genres, web, codec, bitrate, sample]

        return data

    def edit_mode(self, state):
        self.edit = state

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
        state = self.edit

        if state:
            self.builder.get_object("info_grid").child_set_property(entry, "width", 1)
        else:
            self.builder.get_object("info_grid").child_set_property(entry, "width", 2)

        self.builder.get_object("button_dig").set_visible(state)

        return

    def web_button_state(self, entry):
        url = entry.get_text()
        state = re_url.match(url)

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

        name = row[cursor][0]
        url = row[cursor][1]
        genres = row[cursor][2]
        web = row[cursor][3]
        codec = row[cursor][4]
        bitrate = row[cursor][5]
        sample = row[cursor][6]

        self.builder.get_object("text_name").set_text(name)
        self.builder.get_object("text_url").set_text(url)
        self.builder.get_object("text_genres").set_text(genres)
        self.builder.get_object("text_web").set_text(web)
        self.builder.get_object("text_codec").set_text(codec)
        self.builder.get_object("text_bitrate").set_text(str(bitrate))
        self.builder.get_object("text_sample").set_text(str(sample))

        return

    def save_db(self):

        stations = et.Element("stations")

        i = 0
        for row in self.bookmarks:
            server = et.SubElement(stations, "server")
            server.set("index", str(i))

            name = et.SubElement(server, "name")
            url = et.SubElement(server, "url")
            genres = et.SubElement(server, "genres")
            web = et.SubElement(server, "web")
            codec = et.SubElement(server, "codec")
            bitrate = et.SubElement(server, "bitrate")
            sample = et.SubElement(server, "sample")

            name.text = row[0]
            url.text = row[1]
            genres.text = row[2]
            web.text = row[3]
            codec.text = row[4]
            bitrate.text = str(row[5])
            sample.text = str(row[6])

            i += 1

        db = et.ElementTree(stations)
        db_path = path.expanduser("~/.config/streams/stations.xml")

        if not path.exists(path.dirname(db_path)):
            makedirs(path.dirname(db_path))

        db.write(db_path)
        return

    def exit(self, a, b):
        self.write_state()
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
        max = file.readline()
        cmd = file.readline()

        file.close()

        self.window.resize(x, y)
        self.builder.get_object("panel").set_position(pane)

        if max == "True":
            self.window.maximize()

        self.builder.get_object("text_command").set_text(cmd[:-1])

        return

    def command_save(self, item):
        dialog = Gtk.MessageDialog(self.window,
                                   0,
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

        if response != -5:
            return

        cmd = self.builder.get_object("text_command").get_text()
        row = {name: cmd}

        if name in self.list_commands:
            dialog = Gtk.MessageDialog(self.window,
                                       0,
                                       Gtk.MessageType.QUESTION,
                                       Gtk.ButtonsType.OK_CANCEL,
                                       "A command with that name already exists")
            dialog.format_secondary_text("replace {}?".format(name))
            dialog.set_default_response(Gtk.ResponseType.OK)
            response = dialog.run()
            dialog.destroy()

            if response != -5:
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
                                           0,
                                           Gtk.MessageType.QUESTION,
                                           Gtk.ButtonsType.OK_CANCEL,
                                           "You are about to delete an existing command")
                dialog.format_secondary_text("Do you really want to delete the {} command ?".format(key))
                dialog.set_default_response(Gtk.ResponseType.OK)
                response = dialog.run()
                dialog.destroy()

                if response != -5:
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
                                   0,
                                   Gtk.MessageType.ERROR,
                                   Gtk.ButtonsType.CLOSE,
                                   err)
        dialog.set_default_response(Gtk.ResponseType.CLOSE)
        dialog.run()
        dialog.destroy()
        return

    def dig(self, url, button):
        new_url = "fresh"
        i = 0
        while url != new_url and i < 5:
            print("old", url, "new", new_url)

            content_type = None

            if new_url != "fresh":
                url = new_url

            try:
                response = urllib.request.urlopen(url)
                info = response.info()
                content_type = info.get_content_type()
                print(content_type)
            except urllib.error.HTTPError as err:
                dialog = Gtk.MessageDialog(self.window,
                                           0,
                                           Gtk.MessageType.ERROR,
                                           Gtk.ButtonsType.CLOSE,
                                           err.code)
                dialog.format_secondary_text(err.reason)
                dialog.set_default_response(Gtk.ResponseType.CLOSE)
                dialog.run()
                dialog.destroy()
                return "error"
            except http.client.BadStatusLine as err:
                if err.line == "ICY 200 OK\r\n":
                    print("ICY 200 Match")
                    break

            if content_type in pl_types:
                print("Playlist type match")
                data = str(response.read(), "utf-8")
                match = self.parse_playlist(data, content_type)
                response.close()

                if len(match) > 0 and new_url != "fresh" and not button:
                    self.add_playlist(url, data, content_type)
                    return
                else:
                    new_url = match[0][1]

                print("Next URL:", new_url)

            if content_type in audio_types:
                print("Audio type match")
                break

            if new_url == "fresh":
                self.error_popup("Couldn't find audio stream info")
                return "error"

            i += 1

        if i == 5:
            self.error_popup("Couldn't find any audio stream in 5 tries")

        return url

    def add_playlist(self, location, data, mime, source):
        print("Entering add_playlist")
        match = self.parse_playlist(data, mime)

        if len(match) > 1:
            build = Gtk.Builder()
            build.add_from_file(glade_loc)

            dialog = build.get_object("win_multi_playlist")
            select = build.get_object("selection_stations")
            text = build.get_object("label_mp")

            if source == "file":
                b_keep = build.get_object("button_mp_keep")
                b_keep.set_sensitive(False)

            text.set_text("Playlist\n{}\nhas several entries.\nPlease select which one(s) you want to add.".format(location))

            stations_list = build.get_object("stations")

            for station in match:
                stations_list.append(station)

            response = dialog.run()
            print("add_playlist response", response)
            if response == -5:
                model, pathlist = select.get_selected_rows()

                for row in pathlist:
                    self.add_station(stations_list[row][1])

            elif response == 1:
                self.add_url(location)

            dialog.destroy()

        elif len(match) == 1 and source == "web":
            self.add_url(location)

        elif len(match) == 1 and source == "file":
            self.add_url(match[0][1])

        return

    @staticmethod
    def parse_playlist(data, mime):
        print("Entering parse_playlist")
        result = []

        if mime == "audio/x-scpls" or mime == "application/pls+xml":
            print("Parsing as x-scpls")
            titles = re_pls_title.findall(data)
            urls = re_pls_url.findall(data)

            ents = re.search(r"numberofentries=(\d)", data)
            entries = int(ents.group(1))

            tits = {}
            for t in titles:
                id = int(t[0])
                title = t[1]
                row = {id: title}
                tits.update(row)

            locs = {}
            for u in urls:
                id = int(u[0])
                url = u[1]
                row = {id: url}
                locs.update(row)

            for i in range(1, entries + 1):
                row = (tits[i], locs[i])
                result.append(row)

        elif mime == "audio/x-mpegurl" or mime == "audio/mpegurl":
            print("Parsing as x-mpegurl")
            if re.match(r"^#EXTM3U.*", data):
                print("Extended")
                pairs = re_m3u_infos.findall(data)

                for title, url in pairs:
                    row = (title, url)
                    result.append(row)
            else:
                print("Simple")
                match = re_url.findall(data)
                for url in match:
                    row = (url, url)
                    result.append(row)

        elif mime == "application/xspf+xml":
            print("Parsing as xspf+xml")
            root = et.fromstring(data)

            for track in root.iter("{http://xspf.org/ns/0/}track"):
                loc = track.find("{http://xspf.org/ns/0/}location")
                tit = track.find("{http://xspf.org/ns/0/}title")

                location = loc.text

                if tit is None:
                    title = location
                else:
                    title = tit.text

                row = (title, location)
                result.append(row)

            print("Parsed with", len(result), "entries")

        return result

    def add_from_file(self, location):
        mime = mimetypes.guess_type(location)
        print("mime", mime)
        file = open(location, "r")
        data = file.read()
        file.close()
        self.add_playlist(location, data, mime[0], "file")


if __name__ == '__main__':
    GObject.threads_init()
    Gst.init(None)
    MainWindow()
    Gtk.main()