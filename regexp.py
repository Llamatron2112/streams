import re

URL_REGEX = r"(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|" \
                r"[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+" \
                r"[.][a-z]{2,4}/)(?:[^\s()<>]+|\((?:[^\s()" \
                r"<>]+|(?:\([^\s()<>]+\)))*\))+(?:\((?:[^\s()<>]+" \
                r"|(?:\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'\".,<>?«»“”‘’]))"

RE_URL = re.compile(URL_REGEX)
