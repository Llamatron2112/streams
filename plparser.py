import re
from xml.etree import ElementTree as Et

from constants import RE_URL, URL_REGEX

RE_M3U_URL = RE_URL
RE_M3U_INFOS = re.compile(r"#EXTINF:-1,(.*)\n{}".format(URL_REGEX))

RE_PLS_URL = re.compile(r"File(\d+)={}\n".format(URL_REGEX))
RE_PLS_TITLE = re.compile(r"Title(\d+)=(.*)\n")


def parse_pls(data):
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

    result = []
    for i in range(1, entries + 1):
        if tits[i] is not None:
            row = (tits[i], locs[i])
        else:
            row = (locs[i], locs[i])
        result.append(row)

    return result


def parse_m3u(data):
    result = []
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

    return result


def parse_xspf(data):
    root = Et.fromstring(data)
    result = []
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

    return result


def parse_unknown(data):
    match = RE_URL.findall(data)
    result = []
    for url in match:
        row = (url, url)
        result.append(row)

    return result


class PlaylistParser:
    _parsers = {"audio/x-scpls": parse_pls,
                "application/pls+xml": parse_pls,
                "audio/mpegurl": parse_m3u,
                "audio/x-mpegurl": parse_m3u,
                "application/xspf+xml": parse_xspf
                }

    def parse(self, data, mime):
        return self._parsers.get(mime, parse_unknown)(data)
