import gi
gi.require_version("Gtk", "3.0")
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gtk, GstPbutils

import http
from http.client import error

import urllib
from urllib import request, error

import re

from xml.etree import ElementTree as Et

import mimetypes

URL_REGEX = r"(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|" \
            r"[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+" \
            r"[.][a-z]{2,4}/)(?:[^\s()<>]+|\((?:[^\s()" \
            r"<>]+|(?:\([^\s()<>]+\)))*\))+(?:\((?:[^\s()<>]+" \
            r"|(?:\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'\".,<>?«»“”‘’]))"
RE_URL = re.compile(URL_REGEX)

RE_M3U_URL = RE_URL
RE_M3U_INFOS = re.compile(r"#EXTINF:-1,(.*)\n{}".format(URL_REGEX))

RE_PLS_URL = re.compile(r"File(\d+)={}\n".format(URL_REGEX))
RE_PLS_TITLE = re.compile(r"Title(\d+)=(.*)\n")

PL_TYPES = ["audio/x-scpls",
            "audio/mpegurl",
            "audio/x-mpegurl",
            "application/xspf+xml",
            "application/pls+xml",
            "application/octet-stream"]

AUDIO_TYPES = ["audio/mpeg",
               "application/ogg",
               "audio/ogg",
               "audio/aac",
               "audio/aacp"]

HLS_TYPES = ["application/vnd.apple.mpegurl",
             "application/x-mpegurl"]


class Station:
    def __init__(self, app, location, db, parent, file=False):
        self.db = db
        self.app = app
        self.add_station(location, parent, file)

    def add_station(self, location, parent=None, file=False):

        if file:
            mime = mimetypes.guess_type(location)
            if mime[0] in HLS_TYPES:
                self.app.error_popup("HLS streams can't be added from a file\n\nPlease copy/paste the link")
                return

            file = open(location, "r")
            data = file.read()
            file.close()
            self.add_playlist(location, data, mime[0], None, True)

        else:
            content_type = None
            response = None
            try:
                response = urllib.request.urlopen(location)
                info = response.info()
                content_type = info.get_content_type()

            except urllib.error.HTTPError as err:
                dialog = Gtk.MessageDialog(self.app.window,
                                           Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
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
                    self.add_url(location, parent)
                    return

            if content_type in PL_TYPES:
                data = str(response.read(), "utf-8")
                response.close()
                self.add_playlist(location, data, content_type, parent, False)

            elif content_type in AUDIO_TYPES:
                response.close()
                self.add_url(location, parent)

            elif content_type in HLS_TYPES:
                response.close()
                self.add_hls(location, parent)

            else:
                response.close()
                self.app.error_popup("Unknown content type: {}".format(content_type))

    def add_url(self, url, parent=None):
        infos = Station.fetch_infos(self, url)
        infos.append(False)
        infos.append(400)
        self.db.append(parent, infos)
        return

    def add_hls(self, url, parent=None):
        infos = str(urllib.request.urlopen(url).read(), "utf-8")
        br = re.findall(r"BANDWIDTH=(\d*)", infos)
        bitrate = int(br[0]) / 1000
        cod = re.findall(r"CODECS=\"(.*)\"", infos)
        codec = cod[0]
        row = (url, url, "", "", codec, bitrate, 0, False, 400)
        self.db.append(parent, row)
        return

    def add_playlist(self, location, data, mime, parent=None, file=False):
        match = Station.parse_playlist(data, mime)

        if len(match) > 1:
            dialog = Gtk.Dialog("Multiple entries",
                                self.app.window,
                                Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
            dialog.add_button(Gtk.STOCK_CANCEL, -6)
            dialog.add_button("Add selected", Gtk.ResponseType.OK)
            dialog.add_button("Create Folder", 2)

            if not file:
                dialog.add_button("Keep playlist", 1)

            stations = Gtk.ListStore(str, str)
            for station in match:
                stations.append(station)

            view = Gtk.TreeView(stations)
            view.show()

            select = view.get_selection()
            select.set_mode(Gtk.SelectionMode.MULTIPLE)

            col = Gtk.TreeViewColumn(None, Gtk.CellRendererText(), text=0)
            view.append_column(col)

            scroll_area = Gtk.ScrolledWindow()
            scroll_area.add(view)
            scroll_area.show()

            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.set_default_size(400, 300)

            dialog.vbox.pack_start(scroll_area, True, True, 5)

            response = dialog.run()

            if response == Gtk.ResponseType.OK:
                model, pathlist = select.get_selected_rows()
                for row in pathlist:
                    self.add_station(stations[row][1])

            if response == 2:
                fold_dialog = Gtk.MessageDialog(dialog,
                                                Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                                Gtk.MessageType.QUESTION,
                                                Gtk.ButtonsType.OK_CANCEL,
                                                "Enter the new folder's name"
                                                )
                text_fold = Gtk.Entry()
                text_fold.set_activates_default(Gtk.ResponseType.OK)
                text_fold.show()
                area = fold_dialog.get_content_area()
                area.add(text_fold)
                fold_dialog.set_default_response(Gtk.ResponseType.OK)

                fol_name = ""

                fold_response = fold_dialog.run()

                if fold_response == Gtk.ResponseType.OK:
                    fol_name = text_fold.get_text()

                fold_dialog.destroy()

                if fol_name != "":
                    fold_row = [fol_name, "", "", "", "", 0, 0, True, 700]
                    parent = self.db.append(None, fold_row)

                    model, pathlist = select.get_selected_rows()
                    for row in pathlist:
                        self.add_station(stations[row][1], parent)

            elif response == 1:
                self.add_url(location)

            dialog.destroy()

        elif len(match) == 1 and not file:
            self.add_url(location, parent)
        elif len(match) == 1 and file:
            self.add_url(match[0][1], parent)

        return

    def fetch_infos(self, url):
        server_url = Station.dig(self, url, True)
        if server_url == "error":
            return "error"

        info = GstPbutils.Discoverer().discover_uri(server_url)

        name = ""
        genres = ""
        web = ""

        tags = info.get_tags()
        n = tags.n_tags() - 1
        for i in range(0, n):
            tag = tags.nth_tag_name(i)
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

        dat = [name, url, genres, web, codec, bitrate, sample]

        return dat

    def dig(self, url, recursive):
        new_url = "fresh"
        i = 0
        while url != new_url and i < 5:
            content_type = None

            if new_url != "fresh":
                url = new_url

            try:
                response = urllib.request.urlopen(url)
                info = response.info()
                content_type = info.get_content_type()
            except urllib.error.HTTPError as err:
                dialog = Gtk.MessageDialog(self.app.window,
                                           Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
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
                    break

            if content_type in PL_TYPES:
                data = str(response.read(), "utf-8")
                match = Station.parse_playlist(data, content_type)
                response.close()

                if len(match) > 0 and new_url != "fresh" and not recursive:
                    Station.add_playlist(url, data, content_type, False)
                    return
                else:
                    new_url = match[0][1]

            if content_type in AUDIO_TYPES:
                break

            if content_type in HLS_TYPES:
                return "Error"

            if new_url == "fresh":
                return "error"

            i += 1

        if i == 5:
            return "error"

        return url

    def parse_playlist(data, mime):
        result = []

        if mime == "audio/x-scpls" or mime == "application/pls+xml":
            titles = RE_PLS_TITLE.findall(data)
            urls = RE_PLS_URL.findall(data)

            ents = re.search(r"numberofentries=(\d+)", data, re.IGNORECASE)
            entries = int(ents.group(1))

            tits = {}
            for t in titles:
                i = int(t[0])
                title = t[1]
                row = {i: title}
                tits.update(row)

            locs = {}
            for u in urls:
                i = int(u[0])
                url = u[1]
                row = {i: url}
                locs.update(row)

            for i in range(1, entries + 1):
                if len(tits) == len(locs):
                    row = (tits[i], locs[i])
                else:
                    row = (locs[i], locs[i])

                result.append(row)

        elif mime == "audio/x-mpegurl" or mime == "audio/mpegurl":
            if re.match(r"^#EXTM3U.*", data):
                pairs = RE_M3U_INFOS.findall(data)

                for title, url in pairs:
                    row = (title, url)
                    result.append(row)
            else:
                match = RE_URL.findall(data)
                for url in match:
                    row = (url, url)
                    result.append(row)

        elif mime == "application/xspf+xml":
            root = Et.fromstring(data)
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

        else:
            match = RE_URL.findall(data)
            for url in match:
                row = (url, url)
                result.append(row)

        return result
