# Minecraft NBT Editor

A desktop GUI editor for Minecraft NBT files with a special focus on player
`*.dat` save data. The application combines a full tree-based NBT editor with
dedicated inventory tooling so that you can view and manipulate player
inventories, Ender chests, and any other tag without manually editing binary
files.

## Features

- **Tree-based editor** – Inspect and edit every tag in the file. Supports all
  standard NBT types (byte, short, int, long, float, double, arrays, strings,
  lists, and compounds).
- **Inline editing** – Rename tags, change numeric or string values, and edit
  array contents using comma-separated input.
- **Structure management** – Add or delete child tags inside compounds and
  lists. List entries automatically adopt the correct subtype when adding the
  first element.
- **Inventory visualisation** – Player inventories are displayed as an
  interactive grid with slot numbers. Click a slot to change the item ID, stack
  size, or to remove the item entirely. Armour, off-hand, and other special
  slots are presented in a dedicated sidebar.
- **Ender chest support** – When the `EnderItems` tag is present an additional
  tab shows the Ender chest inventory with the same editing controls.
- **Save workflow** – Open existing `.dat` or `.nbt` files, edit them, then save
  or save-as with automatic gzip handling provided by `nbtlib`.

## Getting started

1. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Run the editor:

   ```bash
   python main.py
   ```

3. Use **File → Open…** to select a player `*.dat` file or any other NBT file.
   The tree on the left shows the full tag hierarchy. Selecting a tag lets you
   edit its value on the right-hand panel.

4. Switch to the **Inventory view** tab to see player inventory slots and, if
   available, Ender chest contents. Click any slot to edit, add, or remove an
   item. Changes immediately update the tree view.

5. When finished choose **File → Save** or **File → Save As…** to persist your
   modifications.

## Tips

- Lists that do not yet have a subtype will prompt you for the type of the
  first element when you add a child.
- Arrays expect comma-separated integers. Hexadecimal and decimal notation are
  both supported.
- For complex item NBT data (custom names, enchantments, etc.) edit the child
  tags within the tree view after creating or selecting an inventory item.

The editor is built on top of [`nbtlib`](https://nbtlib.readthedocs.io/) and
uses the standard Tk themed widgets, so it runs anywhere Python and Tkinter are
available.
