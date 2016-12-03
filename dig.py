import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import http
from http.client import error

import urllib
from urllib import request, error

from constants import AUDIO_TYPES, PL_TYPES, HLS_TYPES

from plparser import PlaylistParser
from plselect import playlist_selecter

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
                result = playlist_selecter(window, match)
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