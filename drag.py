import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


def drag(data, drop_info, bookmarks, row, cursor):
    if drop_info:
        source_folder = data[7]
        pat, position = drop_info
        dest_iter = bookmarks.get_iter(pat)
        dest_folder = bookmarks.get_value(dest_iter, 7)
        dest_parent = bookmarks.iter_parent(dest_iter)
        if not source_folder:
            if position == Gtk.TreeViewDropPosition.BEFORE:
                new_iter = bookmarks.insert_before(dest_parent, dest_iter, data)
            elif position == Gtk.TreeViewDropPosition.AFTER:
                new_iter = bookmarks.insert_after(dest_parent, dest_iter, data)
            elif dest_folder:
                new_iter = bookmarks.append(dest_iter, data)
            else:
                new_iter = bookmarks.insert_before(dest_parent, dest_iter, data)
        else:
            if dest_parent is not None:
                new_iter = bookmarks.insert_before(None, dest_parent, data)
            elif position == Gtk.TreeViewDropPosition.BEFORE:
                new_iter = bookmarks.insert_before(None, dest_iter, data)
            elif position == Gtk.TreeViewDropPosition.AFTER:
                new_iter = bookmarks.insert_after(None, dest_iter, data)
            else:
                new_iter = bookmarks.insert_before(None, dest_iter, data)
    else:
        new_iter = bookmarks.append(None, data)

    for it in row[cursor].iterchildren():
        dat = []
        for value in it:
            dat.append(value)
        bookmarks.append(new_iter, dat)

    return
