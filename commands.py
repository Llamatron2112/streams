import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import json

from collections import OrderedDict

from os import path, makedirs


class CommandsMenu(Gtk.Menu):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.commands = OrderedDict()
        self.load()
        self.update()

    def add(self, item):
        dialog = Gtk.MessageDialog(self.parent.window,
                                   Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
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

        if response != Gtk.ResponseType.OK:
            return

        cmd = self.parent.builder.get_object("text_command").get_text()
        row = {name: cmd}

        if name in self.commands:
            dialog = Gtk.MessageDialog(self.parent.window,
                                       Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                       Gtk.MessageType.QUESTION,
                                       Gtk.ButtonsType.OK_CANCEL,
                                       "A command with that name already exists")
            dialog.format_secondary_text("replace {}?".format(name))
            dialog.set_default_response(Gtk.ResponseType.OK)
            response = dialog.run()
            dialog.destroy()

            if response != Gtk.ResponseType.OK:
                return

        self.commands.update(row)
        self.update()
        self.save()
        return

    def delete(self, item):
        cmd = self.parent.builder.get_object("text_command").get_text()

        for key in self.commands.keys():
            if self.commands[key] == cmd:
                dialog = Gtk.MessageDialog(self.parent.window,
                                           Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                                           Gtk.MessageType.QUESTION,
                                           Gtk.ButtonsType.OK_CANCEL,
                                           "You are about to delete an existing command")
                dialog.format_secondary_text("Do you really want to delete the {} command ?".format(key))
                dialog.set_default_response(Gtk.ResponseType.OK)
                response = dialog.run()
                dialog.destroy()

                if response != Gtk.ResponseType.OK:
                    return

                del self.commands[key]
                self.update()
                self.save()
                return

        self.parent.popup("Command doesn't match any saved command")
        return

    def activated(self, item):
        command = self.commands[item.get_label()]
        self.parent.builder.get_object("text_command").set_text(command)
        return

    def update(self):
        for widget in self.get_children():
            widget.destroy()

        button_save = Gtk.MenuItem.new_with_label("Save Command")
        button_save.connect("activate", self.add)
        button_save.show()

        button_delete = Gtk.MenuItem.new_with_label("Delete Command")
        button_delete.connect("activate", self.delete)
        button_delete.show()

        menu_separator = Gtk.SeparatorMenuItem()
        menu_separator.show()

        self.append(button_save)
        self.append(button_delete)
        self.append(menu_separator)

        for key in self.commands.keys():
            choice = Gtk.MenuItem.new_with_label(key)
            choice.connect("activate", self.activated)
            self.append(choice)
            choice.show()

        return

    def save(self):
        commands_file = path.expanduser("~/.config/streams/commands.json")

        if not path.exists(path.dirname(commands_file)):
            makedirs(path.dirname(commands_file))

        file = open(commands_file, 'w')
        json.dump(self.commands, file)
        file.close()
        return

    def load(self):
        commands_file = path.expanduser("~/.config/streams/commands.json")

        if path.exists(commands_file):
            file = open(commands_file, 'r')
            self.commands = json.load(file, object_pairs_hook=OrderedDict)
            file.close()
        else:
            self.commands = {"Audacious": "audacious {}",
                             "Rhythmbox": "rhythmbox {}"}

        return
