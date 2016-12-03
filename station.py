import gi
gi.require_version("Gtk", "3.0")
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gtk, GstPbutils

import http
from http.client import error

import urllib
from urllib import request, error

from subprocess import getoutput

import re

import mimetypes

from plparser import PlaylistParser

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

FFMPEG = False


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
        infos[1] = url
        self.db.append(parent, infos)
        return

    def add_hls(self, url, parent=None):
        infos = str(urllib.request.urlopen(url).read(), "utf-8")
        br = re.findall(r"BANDWIDTH=(\d*)", infos)
        bitrate = int(br[0]) / 1000
        cod = re.findall(r"CODECS=\"(.*)\"", infos)
        codec = cod[0]
        row = (url, url, "", "", codec, bitrate, "", False, 400)
        self.db.append(parent, row)
        return

    def add_playlist(self, location, data, mime, parent=None, file=False):
        match = PlaylistParser().parse(data, mime)

        if len(match) > 1:
            response = Station.playlist_selecter(self.app.window, match, file)
            if type(response) is tuple:
                if response[0] is not None:
                    par_row = [response[0], "", "", "", "", "", "", True, 700]
                    par = self.db.append(None, par_row)
                else:
                    par = None
                for row in response[1]:
                    self.add_station(row, par)

            elif response == "cancel":
                return

            elif response == "keep":
                self.add_url(location, parent)

        elif len(match) == 1 and not file:
            self.add_url(location, parent)

        elif len(match) == 1 and file:
            self.add_url(match[0][1], parent)

        return

    def fetch_infos(self, url):
        server_url = Station.dig(self, url, True)
        if server_url == "error":
            return "error"

        if FFMPEG:
            data = Station.fetch_ffmpeg(server_url)
        else:
            data = Station.fetch_gst(server_url)

        return data

    @staticmethod
    def fetch_gst(url):

        info = GstPbutils.Discoverer().discover_uri(url)

        name = ""
        genres = ""
        web = ""

        tags = info.get_tags()
        n = tags.n_tags()
        for i in range(0, n):
            tag = tags.nth_tag_name(i)
            value = tags.get_string(tag)[1]
            print(i, ":", tag, "-->", value)
            if tag == "organization":
                name = value
            elif tag == "genre":
                genres = value
            elif tag == "location":
                web = value

        stream_list = info.get_stream_list()
        audio_stream = stream_list[0]
        bitrate = str(int(audio_stream.get_bitrate() / 1000))
        sample = str(audio_stream.get_sample_rate())

        caps = audio_stream.get_caps()
        codec = GstPbutils.pb_utils_get_codec_description(caps)

        if bitrate == "0" or name == "" or genres == "" or web == "":
            req = urllib.request.urlopen(url)
            head = req.info()
            req.close()
            for tag in head.items():
                match = re.match(r"ic[ey]-([a-z]+)", tag[0])
                if match:
                    print(match.group(1) + ": " + tag[1])
                    tagname = match.group(1)
                    tagvalue = tag[1]
                    if tagname == "br" or tagname == "bitrate":
                        bitrate = tagvalue
                    elif tagname == "name":
                        name = tagvalue
                    elif tagname == "genre":
                        genres = tagvalue
                    elif tagname == "url":
                        web = tagvalue

        if bitrate == "0":
            bitrate = "N/A"

        if name == "":
            name = url

        dat = [name, url, genres, web, codec, bitrate, sample]

        return dat

    @staticmethod
    def fetch_ffmpeg(url):
        text = getoutput("ffprobe {}".format(url))
        lines = str.splitlines(text)

        values = {}
        values.update({"br": ""})
        values.update({"name": ""})
        values.update({"genre": ""})
        values.update({"url": ""})

        for line in lines:
            match = re.search(r"icy-([a-zA-Z0-9]+)\s+:\s+(.*)", line)
            if match is not None:
                print(match.group(1), ":", match.group(2))
                values.update({match.group(1): match.group(2)})

        m_audio = re.search(r"Stream #0:0.*Audio: (.*), ([0-9]+) Hz", text)
        values.update({"codec": m_audio.group(1)})
        values.update({"sample": m_audio.group(2)})

        if values["br"] == "":
            m_br = re.search(r"Duration.* bitrate: (.*)(?: kb/s)?", text)
            if m_br is None:
                values.update({"br": "N/A"})
            else:
                values.update({"br": m_br.group(1)})

        if values["name"] == "":
            values.update({"name": url})

        dat = [values["name"],
               url,
               values["genre"],
               values["url"],
               values["codec"],
               values["br"],
               values["sample"]]

        return dat

    @staticmethod
    def dig(window, url, recursive):
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
                print(content_type)
            except urllib.error.HTTPError as err:
                dialog = Gtk.MessageDialog(window,
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
                    print("ICY 200 OK")
                    break

            if content_type in PL_TYPES:
                data = str(response.read(), "utf-8")
                response.close()
                match = PlaylistParser().parse(data, content_type)
                if len(match) > 1 and not recursive:
                    result = Station.playlist_selecter(window, match)
                    if result == "cancel":
                        return
                    elif result == "keep":
                        return url
                    elif type(result) is list:
                        res = []
                        for row in result[1]:
                            res.append(row)
                        return result[0], res

                else:
                    new_url = match[0][1]
                    if new_url is None:
                        # Empty playlist
                        return "error"

            if content_type in AUDIO_TYPES:
                break

            if content_type in HLS_TYPES:
                return "error"

            if new_url == "fresh":
                # No new url
                return "error"

            if not recursive and new_url != url:
                return new_url

            i += 1

        if i == 5:
            return "error"

        return url

    @staticmethod
    def playlist_selecter(window, match, file=False):
        dialog = Gtk.Dialog("Multiple entries",
                            window,
                            Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
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

        result = []

        if response == Gtk.ResponseType.OK:
            model, pathlist = select.get_selected_rows()
            for row in pathlist:
                result.append(stations[row][1])

            dialog.destroy()
            return None, result

        elif response == 2:
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
                model, pathlist = select.get_selected_rows()
                for row in pathlist:
                    result.append(stations[row][1])

                dialog.destroy()
                return fol_name, result

        elif response == 1:
            dialog.destroy()
            return "keep"

        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()
            return "cancel"
