class Export:
    def __init__(self, file, db, fold_path):
        self.db = db
        self.folder_path = fold_path
        ext = file.split(".")[-1].lower()
        self.count = 0
        if ext == "m3u":
            self.data = "#EXTM3U\n"
            db.foreach(self._export_m3u)
        elif ext == "pls":
            self.data = str()
            db.foreach(self._export_pls)
            head = "[playlist]\nNumberOfEntries={}\n".format(self.count)
            self.data = head + self.data

    def _export_m3u(self, model, path, iter):
        row = self.db.get(iter, 0, 1, 7)
        if not row[2] and (self.folder_path is None or self.folder_path[0] == path[0]):
            self.count += 1
            self.data += "#EXTINF:-1,{}\n".format(row[0])
            self.data += "{}\n".format(row[1])

        return

    def _export_pls(self, mode, path, iter):
        row = self.db.get(iter, 0, 1, 7)
        if not row[2] and (self.folder_path is None or self.folder_path[0] == path[0]):
            self.count += 1
            self.data += "File{}={}\n".format(self.count, row[1])
            self.data += "Title{}={}\n".format(self.count, row[0])

        return
