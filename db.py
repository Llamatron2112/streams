import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from xml.etree import ElementTree as Et
from os import path, makedirs

from export import Export


class DataBase(Gtk.TreeStore):
    def add_folder(self, name):
        it = self.append(None, [name, "", "", "", "", "", "", True, 700])
        return it

    def add_row(self, parent, row):
        it = self.append(parent, row)
        return it

    def save(self):
        print("DB save")
        stations = Et.Element("stations")
        self.foreach(self._add_row_to_xml, stations)

        db = Et.ElementTree(stations)
        db_path = path.expanduser("~/.config/streams/stations.xml")

        if not path.exists(path.dirname(db_path)):
            makedirs(path.dirname(db_path))

        db.write(db_path)
        return

    def _add_row_to_xml(self, model, path, treeiter, user_data):
        row = self.get(treeiter, 0, 1, 2, 3, 4, 5, 6, 7)
        server = Et.SubElement(user_data, "server")
        server.text = row[0]
        server.set("url", row[1])
        server.set("genres", row[2])
        server.set("web", row[3])
        server.set("codec", row[4])
        server.set("bitrate", row[5])
        server.set("sample", row[6])
        server.set("folder", str(row[7]))

        parent_iter = self.iter_parent(treeiter)
        if parent_iter is not None:
            parent = self.get_path(parent_iter)
        else:
            parent = ""
        server.set("parent", parent)

    def load(self):
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
            row.append(server.get("bitrate"))
            row.append(server.get("sample"))

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
                parent = self.get_iter(parent_path)

            self.append(parent, row)
        return

    def export(self, file, fold_path=None):
        exp = Export(file, self, fold_path)

        f = open(file, "w")
        f.write(exp.data)
        f.close()

        return
