import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


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
