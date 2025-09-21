"""Minecraft NBT editor with a full-featured GUI.

This tool provides a tree-based editor for any NBT file and specialised
visualisations for player inventories so that player ``.dat`` files can be
edited without manual NBT manipulation.
"""
from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox
from typing import Any, Dict, Iterable, List as PyList, Optional, Tuple, Union

from tkinter import ttk

import nbtlib
from nbtlib import (
    Byte,
    ByteArray,
    Compound,
    Double,
    Float,
    Int,
    IntArray,
    List as NbtList,
    Long,
    LongArray,
    Short,
    String,
)

# -----------------------------------------------------------------------------
# Constants and helpers
# -----------------------------------------------------------------------------

TAG_CLASS_MAP: Dict[str, Any] = {
    "Byte": Byte,
    "Short": Short,
    "Int": Int,
    "Long": Long,
    "Float": Float,
    "Double": Double,
    "String": String,
    "ByteArray": ByteArray,
    "IntArray": IntArray,
    "LongArray": LongArray,
    "Compound": Compound,
    "List": NbtList,
}

CLASS_NAME_MAP: Dict[Any, str] = {cls: name for name, cls in TAG_CLASS_MAP.items()}
NUMERIC_TYPES = (Byte, Short, Int, Long)
FLOAT_TYPES = (Float, Double)
ARRAY_TYPES = (ByteArray, IntArray, LongArray)

INVENTORY_GRID = [
    [9, 10, 11, 12, 13, 14, 15, 16, 17],
    [18, 19, 20, 21, 22, 23, 24, 25, 26],
    [27, 28, 29, 30, 31, 32, 33, 34, 35],
    [0, 1, 2, 3, 4, 5, 6, 7, 8],
]
ENDER_GRID = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8],
    [9, 10, 11, 12, 13, 14, 15, 16, 17],
    [18, 19, 20, 21, 22, 23, 24, 25, 26],
]
SPECIAL_PLAYER_SLOTS = [103, 102, 101, 100, 150]
SPECIAL_SLOT_NAMES = {
    100: "Boots",
    101: "Leggings",
    102: "Chestplate",
    103: "Helmet",
    150: "Offhand",
}


@dataclass
class NodeInfo:
    """Metadata stored for each tree item."""

    tag: Any
    parent: Optional[Union[Compound, NbtList]]
    key: Optional[Union[str, int]]
    path: Tuple[Union[str, int], ...]


class AddTagDialog:
    """Dialog that gathers information for a new tag."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        title: str,
        require_name: bool,
        type_options: Iterable[str],
        preselected_type: Optional[str] = None,
        allow_type_selection: bool = True,
        value_hint: Optional[str] = None,
    ) -> None:
        self.master = master
        self.require_name = require_name
        self.allow_type_selection = allow_type_selection
        self.result: Optional[Dict[str, Any]] = None

        self.top = tk.Toplevel(master)
        self.top.title(title)
        self.top.transient(master)
        self.top.grab_set()

        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar(value=preselected_type or "")
        self.value_var = tk.StringVar()
        self.value_hint = value_hint

        container = ttk.Frame(self.top, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(0, weight=1)

        row = 0
        if require_name:
            ttk.Label(container, text="Name:").grid(row=row, column=0, sticky="w", padx=(0, 8))
            name_entry = ttk.Entry(container, textvariable=self.name_var)
            name_entry.grid(row=row, column=1, columnspan=2, sticky="we")
            row += 1

        ttk.Label(container, text="Type:").grid(row=row, column=0, sticky="w", padx=(0, 8))
        self.type_combo = ttk.Combobox(
            container,
            state="readonly" if allow_type_selection else "disabled",
            values=list(type_options),
            textvariable=self.type_var,
        )
        if preselected_type:
            self.type_combo.set(preselected_type)
        self.type_combo.grid(row=row, column=1, columnspan=2, sticky="we")
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_change)
        row += 1

        ttk.Label(container, text="Value:").grid(row=row, column=0, sticky="nw", padx=(0, 8))
        self.value_entry = ttk.Entry(container, textvariable=self.value_var)
        self.value_entry.grid(row=row, column=1, columnspan=2, sticky="we")
        row += 1

        self.hint_label = ttk.Label(container, text=value_hint or "", wraplength=320)
        if value_hint:
            self.hint_label.grid(row=row, column=0, columnspan=3, sticky="we", pady=(4, 0))
            row += 1

        button_row = ttk.Frame(container)
        button_row.grid(row=row, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(button_row, text="Add", command=self._on_submit).pack(side=tk.RIGHT)

        container.columnconfigure(1, weight=1)
        container.columnconfigure(2, weight=1)

        self._on_type_change()
        self.top.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_type_change(self, *_: Any) -> None:
        type_name = self.type_var.get()
        if type_name in {"Compound", "List"}:
            self.value_entry.configure(state="disabled")
            self.value_var.set("")
        else:
            self.value_entry.configure(state="normal")

    def _on_cancel(self) -> None:
        self.result = None
        self.top.destroy()

    def _on_submit(self) -> None:
        type_name = self.type_var.get().strip()
        if not type_name:
            messagebox.showerror("Missing type", "Choose a tag type for the new entry.", parent=self.top)
            return
        if self.require_name:
            name = self.name_var.get().strip()
            if not name:
                messagebox.showerror("Missing name", "Provide a unique name for the new tag.", parent=self.top)
                return
        else:
            name = None

        value = self.value_var.get().strip()
        if type_name not in {"Compound", "List"} and not value:
            messagebox.showerror("Missing value", "Enter a value for the new tag.", parent=self.top)
            return

        self.result = {"name": name, "type": type_name, "value": value}
        self.top.destroy()

    def show(self) -> Optional[Dict[str, Any]]:
        self.master.wait_window(self.top)
        return self.result


class ItemEditorDialog:
    """Dialog that edits an inventory entry."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        slot: int,
        item: Optional[Compound],
        title: str,
    ) -> None:
        self.master = master
        self.result: Optional[Dict[str, Any]] = None
        self.slot = slot
        self.item = item

        self.top = tk.Toplevel(master)
        self.top.title(title)
        self.top.transient(master)
        self.top.grab_set()

        container = ttk.Frame(self.top, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(0, weight=1)

        self.slot_var = tk.StringVar(value=str(slot))
        self.id_var = tk.StringVar(value=str(item["id"]) if item and "id" in item else "")
        self.count_var = tk.StringVar(value=str(int(item["Count"]) if item and "Count" in item else 1))

        ttk.Label(container, text="Slot:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(container, textvariable=self.slot_var).grid(row=0, column=1, sticky="we")

        ttk.Label(container, text="Item ID:").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(container, textvariable=self.id_var).grid(row=1, column=1, sticky="we")

        ttk.Label(container, text="Count:").grid(row=2, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(container, textvariable=self.count_var).grid(row=2, column=1, sticky="we")

        button_row = ttk.Frame(container)
        button_row.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(side=tk.RIGHT, padx=(8, 0))
        if item is not None:
            ttk.Button(button_row, text="Delete", command=self._on_delete).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(button_row, text="Save", command=self._on_save).pack(side=tk.RIGHT)

        container.columnconfigure(1, weight=1)
        self.top.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _parse_int(self, value: str, *, allow_negative: bool = True) -> Optional[int]:
        try:
            number = int(value, 0)
        except ValueError:
            return None
        if not allow_negative and number < 0:
            return None
        return number

    def _on_save(self) -> None:
        slot_value = self._parse_int(self.slot_var.get().strip())
        if slot_value is None:
            messagebox.showerror("Invalid slot", "Slot must be an integer.", parent=self.top)
            return

        item_id = self.id_var.get().strip()
        if not item_id:
            messagebox.showerror("Invalid item ID", "Provide the full identifier of the item (e.g. minecraft:stone).", parent=self.top)
            return

        count_value = self._parse_int(self.count_var.get().strip(), allow_negative=False)
        if count_value is None or not (0 <= count_value <= 64):
            messagebox.showerror("Invalid count", "Count must be between 0 and 64.", parent=self.top)
            return

        self.result = {
            "action": "save",
            "slot": slot_value,
            "id": item_id,
            "count": count_value,
        }
        self.top.destroy()

    def _on_delete(self) -> None:
        self.result = {"action": "delete"}
        self.top.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.top.destroy()

    def show(self) -> Optional[Dict[str, Any]]:
        self.master.wait_window(self.top)
        return self.result


class NBTEditorApp(tk.Tk):
    """Main application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Minecraft NBT Editor")
        self.geometry("1200x720")

        self.nbt_file: Optional[nbtlib.File] = None
        self.nbt_data: Optional[Compound] = None
        self.file_path: Optional[str] = None

        self.node_map: Dict[str, NodeInfo] = {}
        self.path_to_id: Dict[Tuple[Union[str, int], ...], str] = {}
        self.current_item: Optional[str] = None
        self.current_info: Optional[NodeInfo] = None
        self.current_path: Optional[Tuple[Union[str, int], ...]] = None

        self._create_menu()
        self._create_layout()

    # ------------------------------------------------------------------
    # UI creation
    # ------------------------------------------------------------------
    def _create_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open…", command=self.open_file)
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_command(label="Save As…", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        self.config(menu=menu_bar)

    def _create_layout(self) -> None:
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Tree view
        tree_frame = ttk.Frame(main_pane)
        self.tree = ttk.Treeview(tree_frame, columns=("value", "type"), show="tree headings")
        self.tree.heading("#0", text="Name")
        self.tree.heading("value", text="Value")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=260, anchor="w")
        self.tree.column("value", width=240, anchor="w")
        self.tree.column("type", width=120, anchor="w")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        main_pane.add(tree_frame, weight=1)

        # Right pane with details and inventory
        right_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL)
        main_pane.add(right_pane, weight=2)

        detail_frame = ttk.LabelFrame(right_pane, text="Tag editor", padding=8)
        right_pane.add(detail_frame, weight=1)
        detail_frame.columnconfigure(1, weight=1)
        detail_frame.columnconfigure(2, weight=1)
        detail_frame.rowconfigure(4, weight=1)

        self.path_var = tk.StringVar(value="(nothing selected)")
        self.type_var = tk.StringVar(value="")
        self.name_var = tk.StringVar(value="")
        self.value_var = tk.StringVar(value="")
        self.value_hint_var = tk.StringVar(value="")

        ttk.Label(detail_frame, text="Path:").grid(row=0, column=0, sticky="nw", padx=(0, 8))
        ttk.Label(detail_frame, textvariable=self.path_var, wraplength=360).grid(
            row=0, column=1, columnspan=2, sticky="we"
        )

        ttk.Label(detail_frame, text="Type:").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(detail_frame, textvariable=self.type_var).grid(row=1, column=1, sticky="w")

        ttk.Label(detail_frame, text="Name:").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.name_entry = ttk.Entry(detail_frame, textvariable=self.name_var)
        self.name_entry.grid(row=2, column=1, columnspan=2, sticky="we")

        ttk.Label(detail_frame, text="Value:").grid(row=3, column=0, sticky="nw", padx=(0, 8))
        self.value_entry = ttk.Entry(detail_frame, textvariable=self.value_var)
        self.value_entry.grid(row=3, column=1, columnspan=2, sticky="we")

        self.value_text = tk.Text(detail_frame, height=6, wrap="word")
        self.value_text.grid(row=3, column=1, columnspan=2, sticky="nsew")
        self.value_text.grid_remove()

        self.value_message = ttk.Label(detail_frame, text="", wraplength=360)
        self.value_message.grid(row=3, column=1, columnspan=2, sticky="we")
        self.value_message.grid_remove()

        ttk.Label(detail_frame, textvariable=self.value_hint_var, wraplength=360, foreground="#555555").grid(
            row=4, column=0, columnspan=3, sticky="we", pady=(6, 0)
        )

        button_row = ttk.Frame(detail_frame)
        button_row.grid(row=5, column=0, columnspan=3, pady=(12, 0), sticky="we")
        self.apply_button = ttk.Button(button_row, text="Apply changes", command=self.apply_changes, state="disabled")
        self.apply_button.pack(side=tk.LEFT)
        self.add_button = ttk.Button(button_row, text="Add child", command=self.add_child, state="disabled")
        self.add_button.pack(side=tk.LEFT, padx=(8, 0))
        self.delete_button = ttk.Button(button_row, text="Delete", command=self.delete_node, state="disabled")
        self.delete_button.pack(side=tk.RIGHT)

        # Inventory view
        inventory_frame = ttk.LabelFrame(right_pane, text="Inventory view", padding=8)
        right_pane.add(inventory_frame, weight=1)
        inventory_frame.columnconfigure(0, weight=1)
        inventory_frame.rowconfigure(0, weight=1)

        self.inventory_notebook = ttk.Notebook(inventory_frame)
        self.inventory_notebook.grid(row=0, column=0, sticky="nsew")

        self.value_editor_mode: str = "entry"
        self._show_value_entry()
        self._clear_selection()

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def open_file(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Open NBT file",
            filetypes=[
                ("NBT files", "*.nbt"),
                ("Player data", "*.dat"),
                ("All files", "*.*"),
            ],
        )
        if not filename:
            return
        try:
            nbt_file = nbtlib.load(filename)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to open file", str(exc), parent=self)
            return

        self.nbt_file = nbt_file
        self.nbt_data = nbt_file.root
        self.file_path = filename
        self._update_title()
        self.refresh_views()

    def save_file(self) -> None:
        if not self.nbt_file or not self.file_path:
            messagebox.showinfo("No file", "Load a file before attempting to save.", parent=self)
            return
        try:
            self.nbt_file.save(self.file_path)
            messagebox.showinfo("Saved", f"Changes saved to {self.file_path}", parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to save", str(exc), parent=self)

    def save_file_as(self) -> None:
        if not self.nbt_file:
            messagebox.showinfo("No file", "Load a file before attempting to save.", parent=self)
            return
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Save NBT file",
            defaultextension=".dat",
            filetypes=[("NBT files", "*.nbt"), ("Player data", "*.dat"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            self.nbt_file.save(filename)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to save", str(exc), parent=self)
            return
        self.file_path = filename
        self._update_title()
        messagebox.showinfo("Saved", f"Changes saved to {self.file_path}", parent=self)

    def _update_title(self) -> None:
        if self.file_path:
            self.title(f"Minecraft NBT Editor – {os.path.basename(self.file_path)}")
        else:
            self.title("Minecraft NBT Editor")

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------
    def refresh_views(self, select_path: Optional[Tuple[Union[str, int], ...]] = None) -> None:
        self.build_tree(select_path=select_path)
        self.build_inventory_tabs()

    def build_tree(self, select_path: Optional[Tuple[Union[str, int], ...]] = None) -> None:
        self.tree.delete(*self.tree.get_children())
        self.node_map.clear()
        self.path_to_id.clear()

        if not self.nbt_data:
            self._clear_selection()
            return

        root_name = self.nbt_file.root_name if self.nbt_file else "root"
        root_item = self.tree.insert("", "end", text=root_name or "(root)", values=("", type(self.nbt_data).__name__))
        root_info = NodeInfo(tag=self.nbt_data, parent=None, key=None, path=())
        self.node_map[root_item] = root_info
        self.path_to_id[()] = root_item

        self._populate_tree(root_item, self.nbt_data, ())

        target_path = select_path or self.current_path or ()
        item_id = self.path_to_id.get(target_path)
        if item_id:
            self.tree.selection_set(item_id)
            self.tree.see(item_id)
        else:
            self._clear_selection()

    def _populate_tree(
        self,
        parent_id: str,
        tag: Any,
        path: Tuple[Union[str, int], ...],
    ) -> None:
        if isinstance(tag, Compound):
            for key, value in tag.items():
                child_path = path + (key,)
                item_id = self._insert_tree_item(parent_id, key, value, child_path, tag, key)
                self._populate_tree(item_id, value, child_path)
        elif isinstance(tag, NbtList):
            for index, value in enumerate(tag):
                child_path = path + (index,)
                name = f"[{index}]"
                item_id = self._insert_tree_item(parent_id, name, value, child_path, tag, index)
                self._populate_tree(item_id, value, child_path)

    def _insert_tree_item(
        self,
        parent_id: str,
        name: str,
        tag: Any,
        path: Tuple[Union[str, int], ...],
        parent: Optional[Union[Compound, NbtList]],
        key: Optional[Union[str, int]],
    ) -> str:
        value_display = self._format_value(tag)
        type_name = type(tag).__name__
        item_id = self.tree.insert(parent_id, "end", text=name, values=(value_display, type_name))
        self.node_map[item_id] = NodeInfo(tag=tag, parent=parent, key=key, path=path)
        self.path_to_id[path] = item_id
        return item_id

    def _format_value(self, tag: Any) -> str:
        if isinstance(tag, Compound):
            return f"{len(tag)} entries"
        if isinstance(tag, NbtList):
            subtype = CLASS_NAME_MAP.get(tag.subtype, tag.subtype.__name__ if hasattr(tag, "subtype") else "")
            subtype_text = f" of {subtype}" if subtype and tag.subtype.__name__ != "End" else ""
            return f"{len(tag)} items{subtype_text}"
        if isinstance(tag, ARRAY_TYPES):
            return f"{len(tag)} values"
        if isinstance(tag, NUMERIC_TYPES):
            return str(int(tag))
        if isinstance(tag, FLOAT_TYPES):
            return str(float(tag))
        if isinstance(tag, String):
            text = str(tag)
            return text if len(text) <= 40 else text[:37] + "…"
        return str(tag)

    # ------------------------------------------------------------------
    # Selection handling
    # ------------------------------------------------------------------
    def _clear_selection(self) -> None:
        self.path_var.set("(nothing selected)")
        self.type_var.set("")
        self.name_var.set("")
        self.value_var.set("")
        self.value_hint_var.set("")
        self.current_item = None
        self.current_info = None
        self.current_path = None
        self.apply_button.configure(state="disabled")
        self.add_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")
        self._show_value_entry()
        self.value_entry.configure(state="disabled")
        self.value_message.configure(text="Select a tag to view or edit its value.")
        self.value_message.grid()
        self.value_entry.grid_remove()
        self.value_text.grid_remove()

    def _on_tree_select(self, _: Any) -> None:
        selection = self.tree.selection()
        if not selection:
            self._clear_selection()
            return
        item_id = selection[0]
        info = self.node_map.get(item_id)
        if not info:
            self._clear_selection()
            return
        self.current_item = item_id
        self.current_info = info
        self.current_path = info.path
        self._update_detail_panel(info)

    def _update_detail_panel(self, info: NodeInfo) -> None:
        path_str = self._path_to_string(info.path)
        self.path_var.set(path_str or "(root)")
        tag = info.tag
        type_name = type(tag).__name__
        self.type_var.set(type_name)

        if info.parent is not None and isinstance(info.parent, Compound) and isinstance(info.key, str):
            self.name_entry.configure(state="normal")
            self.name_var.set(info.key)
        else:
            self.name_entry.configure(state="disabled")
            self.name_var.set("" if info.key is None else str(info.key))

        if isinstance(tag, Compound) or isinstance(tag, NbtList):
            self._show_value_message("Container tag – use the buttons below to manage children.")
            self.apply_button.configure(
                state="normal" if (info.parent is not None and isinstance(info.parent, Compound)) else "disabled"
            )
        elif isinstance(tag, ARRAY_TYPES):
            self._show_value_text(
                ", ".join(str(int(entry)) for entry in tag),
                "Enter comma-separated integers.",
            )
            self.apply_button.configure(state="normal")
        elif isinstance(tag, NUMERIC_TYPES):
            self._show_value_entry(str(int(tag)), "Enter an integer value.")
            self.apply_button.configure(state="normal")
        elif isinstance(tag, FLOAT_TYPES):
            self._show_value_entry(str(float(tag)), "Enter a floating point value.")
            self.apply_button.configure(state="normal")
        elif isinstance(tag, String):
            self._show_value_entry(str(tag), "Strings can contain any characters.")
            self.apply_button.configure(state="normal")
        else:
            self._show_value_entry(str(tag), "")
            self.apply_button.configure(state="normal")

        if isinstance(tag, (Compound, NbtList)):
            self.add_button.configure(state="normal")
        else:
            self.add_button.configure(state="disabled")

        if info.parent is None:
            self.delete_button.configure(state="disabled")
        else:
            self.delete_button.configure(state="normal")

    def _show_value_entry(self, value: str = "", hint: str = "") -> None:
        self.value_editor_mode = "entry"
        self.value_var.set(value)
        self.value_hint_var.set(hint)
        self.value_entry.configure(state="normal")
        self.value_entry.grid()
        self.value_text.grid_remove()
        self.value_message.grid_remove()

    def _show_value_text(self, value: str, hint: str) -> None:
        self.value_editor_mode = "text"
        self.value_hint_var.set(hint)
        self.value_text.configure(state="normal")
        self.value_text.delete("1.0", tk.END)
        self.value_text.insert("1.0", value)
        self.value_text.grid()
        self.value_entry.grid_remove()
        self.value_message.grid_remove()

    def _show_value_message(self, message: str) -> None:
        self.value_editor_mode = "message"
        self.value_hint_var.set("")
        self.value_message.configure(text=message)
        self.value_message.grid()
        self.value_entry.grid_remove()
        self.value_text.grid_remove()

    def _path_to_string(self, path: Tuple[Union[str, int], ...]) -> str:
        parts: PyList[str] = []
        for element in path:
            if isinstance(element, int):
                if parts:
                    parts[-1] += f"[{element}]"
                else:
                    parts.append(f"[{element}]")
            else:
                parts.append(element if not parts else f".{element}")
        return "".join(parts)

    # ------------------------------------------------------------------
    # Editing operations
    # ------------------------------------------------------------------
    def apply_changes(self) -> None:
        if not self.current_info:
            return
        info = self.current_info
        tag = info.tag
        parent = info.parent
        key = info.key
        select_path = info.path

        # Handle rename when applicable
        if parent is not None and isinstance(parent, Compound) and isinstance(key, str):
            new_name = self.name_var.get().strip()
            if not new_name:
                messagebox.showerror("Invalid name", "Compound entries must have a name.", parent=self)
                return
            if new_name != key and new_name in parent:
                messagebox.showerror("Duplicate name", f"The name '{new_name}' already exists in this compound.", parent=self)
                return
            if new_name != key:
                parent[new_name] = parent.pop(key)
                select_path = info.path[:-1] + (new_name,)
                key = new_name

        if self.value_editor_mode == "message":
            self.refresh_views(select_path=select_path)
            return

        try:
            new_tag = self._create_tag_from_input(type(tag).__name__, self._get_value_input())
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return

        if parent is None:
            # Root can only be replaced if the file holds a compound/list of same type
            self.nbt_file.root = new_tag  # type: ignore[assignment]
            self.nbt_data = new_tag
            select_path = ()
        else:
            parent[key] = new_tag  # type: ignore[index]
        self.refresh_views(select_path=select_path)

    def _get_value_input(self) -> str:
        if self.value_editor_mode == "entry":
            return self.value_var.get()
        if self.value_editor_mode == "text":
            return self.value_text.get("1.0", tk.END).strip()
        return ""

    def _create_tag_from_input(self, type_name: str, value: str) -> Any:
        type_name = type_name.strip()
        tag_class = TAG_CLASS_MAP.get(type_name)
        if tag_class is None:
            raise ValueError(f"Unsupported tag type: {type_name}")

        if tag_class is Compound:
            return Compound()
        if tag_class is NbtList:
            return NbtList([])
        if tag_class is String:
            return String(value)
        if tag_class in NUMERIC_TYPES:
            try:
                return tag_class(int(value, 0))
            except ValueError as exc:
                raise ValueError("Enter a valid integer.") from exc
        if tag_class in FLOAT_TYPES:
            try:
                return tag_class(float(value))
            except ValueError as exc:
                raise ValueError("Enter a valid floating point value.") from exc
        if tag_class is ByteArray:
            values = self._parse_int_list(value, minimum=-128, maximum=127)
            return ByteArray(values)
        if tag_class is IntArray:
            values = self._parse_int_list(value)
            return IntArray(values)
        if tag_class is LongArray:
            values = self._parse_int_list(value)
            return LongArray(values)
        raise ValueError(f"Unsupported tag type: {type_name}")

    def _parse_int_list(
        self,
        text: str,
        *,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> PyList[int]:
        if not text.strip():
            return []
        stripped = text.strip().strip("[]")
        parts = [part.strip() for part in stripped.split(",") if part.strip()]
        numbers: PyList[int] = []
        for part in parts:
            try:
                value = int(part, 0)
            except ValueError as exc:
                raise ValueError("Lists must contain integers separated by commas.") from exc
            if minimum is not None and value < minimum:
                raise ValueError(f"Values must be ≥ {minimum}.")
            if maximum is not None and value > maximum:
                raise ValueError(f"Values must be ≤ {maximum}.")
            numbers.append(value)
        return numbers

    def add_child(self) -> None:
        if not self.current_info:
            return
        tag = self.current_info.tag
        parent_info = self.current_info
        if isinstance(tag, Compound):
            dialog = AddTagDialog(
                self,
                title="Add compound entry",
                require_name=True,
                type_options=TAG_CLASS_MAP.keys(),
                value_hint="For numeric and array types, supply comma-separated values as needed.",
            )
            result = dialog.show()
            if not result:
                return
            name = result["name"]
            type_name = result["type"]
            value = result["value"]
            if name in tag:
                messagebox.showerror("Duplicate name", f"The name '{name}' already exists.", parent=self)
                return
            try:
                new_tag = self._create_tag_from_input(type_name, value)
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=self)
                return
            tag[name] = new_tag
            self.refresh_views(select_path=parent_info.path + (name,))
        elif isinstance(tag, NbtList):
            if tag.subtype.__name__ != "End":
                subtype_name = CLASS_NAME_MAP.get(tag.subtype, tag.subtype.__name__)
                type_options = [subtype_name]
                allow_type = False
            else:
                type_options = list(TAG_CLASS_MAP.keys())
                allow_type = True
            dialog = AddTagDialog(
                self,
                title="Add list entry",
                require_name=False,
                type_options=type_options,
                preselected_type=type_options[0],
                allow_type_selection=allow_type,
                value_hint="For numeric and array types, supply comma-separated values as needed.",
            )
            result = dialog.show()
            if not result:
                return
            type_name = result["type"]
            value = result["value"]
            try:
                new_tag = self._create_tag_from_input(type_name, value)
            except ValueError as exc:
                messagebox.showerror("Invalid value", str(exc), parent=self)
                return

            if tag.subtype.__name__ == "End":
                list_type = TAG_CLASS_MAP.get(type_name)
                if list_type is None:
                    messagebox.showerror("Unsupported type", f"Cannot create list of {type_name}.", parent=self)
                    return
                typed_list_cls = NbtList[list_type]
                new_list = typed_list_cls(tag)
                self._replace_tag(parent_info, new_list)
                tag = new_list
            tag.append(new_tag)
            new_index = len(tag) - 1
            self.refresh_views(select_path=parent_info.path + (new_index,))

    def _replace_tag(self, info: NodeInfo, new_tag: Any) -> None:
        parent = info.parent
        key = info.key
        if parent is None:
            self.nbt_file.root = new_tag  # type: ignore[assignment]
            self.nbt_data = new_tag
        elif isinstance(parent, Compound):
            parent[key] = new_tag  # type: ignore[index]
        elif isinstance(parent, NbtList):
            parent[key] = new_tag  # type: ignore[index]

    def delete_node(self) -> None:
        if not self.current_info or self.current_info.parent is None:
            return
        info = self.current_info
        parent = info.parent
        key = info.key
        if messagebox.askyesno("Delete tag", "Are you sure you want to delete this tag?", parent=self):
            if isinstance(parent, Compound) and isinstance(key, str):
                del parent[key]
            elif isinstance(parent, NbtList) and isinstance(key, int):
                del parent[key]
            self.refresh_views(select_path=info.path[:-1])

    # ------------------------------------------------------------------
    # Inventory handling
    # ------------------------------------------------------------------
    def build_inventory_tabs(self) -> None:
        for child in self.inventory_notebook.winfo_children():
            child.destroy()
        for tab in self.inventory_notebook.tabs():
            self.inventory_notebook.forget(tab)

        if not self.nbt_data:
            frame = ttk.Frame(self.inventory_notebook)
            ttk.Label(frame, text="Load a player data file to view inventory information.").pack(padx=12, pady=12)
            self.inventory_notebook.add(frame, text="Inventory")
            return

        has_tab = False
        if "Inventory" in self.nbt_data:
            frame = ttk.Frame(self.inventory_notebook)
            self.inventory_notebook.add(frame, text="Inventory")
            self._populate_inventory_frame(
                frame,
                self.nbt_data["Inventory"],
                INVENTORY_GRID,
                special_slots=True,
                tag_name="Inventory",
            )
            has_tab = True
        if "EnderItems" in self.nbt_data:
            frame = ttk.Frame(self.inventory_notebook)
            self.inventory_notebook.add(frame, text="Ender Chest")
            self._populate_inventory_frame(
                frame,
                self.nbt_data["EnderItems"],
                ENDER_GRID,
                special_slots=False,
                tag_name="EnderItems",
            )
            has_tab = True

        if not has_tab:
            frame = ttk.Frame(self.inventory_notebook)
            ttk.Label(frame, text="No inventory data found in this file.").pack(padx=12, pady=12)
            self.inventory_notebook.add(frame, text="Inventory")

    def _populate_inventory_frame(
        self,
        frame: ttk.Frame,
        inventory_tag: NbtList,
        grid_layout: PyList[PyList[int]],
        *,
        special_slots: bool,
        tag_name: str,
    ) -> None:
        for child in frame.winfo_children():
            child.destroy()
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        items_by_slot: Dict[int, Compound] = {}
        for item in inventory_tag:
            slot_value = int(item.get("Slot", Byte(0)))
            items_by_slot[slot_value] = item

        grid_container = ttk.Frame(frame)
        grid_container.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        for r, row_slots in enumerate(grid_layout):
            grid_container.rowconfigure(r, weight=1)
            for c, slot in enumerate(row_slots):
                grid_container.columnconfigure(c, weight=1)
                button = ttk.Button(
                    grid_container,
                    text=self._format_slot_button_text(slot, items_by_slot.get(slot)),
                    command=lambda s=slot: self._edit_inventory_item(inventory_tag, s, tag_name),
                    width=18,
                )
                button.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")

        if special_slots:
            all_special = set(SPECIAL_PLAYER_SLOTS)
            all_special.update(slot for slot in items_by_slot if slot not in {slot for row in grid_layout for slot in row})
            if all_special:
                special_frame = ttk.Labelframe(frame, text="Special slots", padding=8)
                special_frame.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=8)
                for slot in sorted(all_special):
                    button = ttk.Button(
                        special_frame,
                        text=self._format_slot_button_text(slot, items_by_slot.get(slot)),
                        command=lambda s=slot: self._edit_inventory_item(inventory_tag, s, tag_name),
                        width=20,
                    )
                    button.pack(fill="x", pady=2)

    def _format_slot_button_text(self, slot: int, item: Optional[Compound]) -> str:
        name = SPECIAL_SLOT_NAMES.get(slot, f"Slot {slot}")
        if item is None:
            return f"{name}\nEmpty"
        item_id = item.get("id")
        item_name = str(item_id) if item_id is not None else "Unknown"
        count_tag = item.get("Count")
        try:
            count = int(count_tag) if count_tag is not None else 1
        except TypeError:
            count = 1
        return f"{name}\n{item_name} ×{count}"

    def _edit_inventory_item(self, inventory_tag: NbtList, slot: int, tag_name: str) -> None:
        item = self._find_inventory_item(inventory_tag, slot)
        dialog = ItemEditorDialog(self, slot=slot, item=item, title=f"Slot {slot}")
        result = dialog.show()
        if not result:
            return

        action = result["action"]
        if action == "delete":
            if item is None:
                messagebox.showinfo("Empty slot", "There is no item to delete in this slot.", parent=self)
                return
            inventory_tag.remove(item)
            self.refresh_views(select_path=(tag_name,))
            return

        new_slot = result["slot"]
        new_id = result["id"]
        new_count = result["count"]

        conflict = self._find_inventory_item(inventory_tag, new_slot, exclude=item)
        if conflict is not None:
            messagebox.showerror("Slot in use", f"Slot {new_slot} already contains an item.", parent=self)
            return

        if item is None:
            new_item = Compound()
            new_item["Slot"] = Byte(new_slot)
            new_item["id"] = String(new_id)
            new_item["Count"] = Byte(new_count)
            inventory_tag.append(new_item)
        else:
            item["Slot"] = Byte(new_slot)
            item["id"] = String(new_id)
            item["Count"] = Byte(new_count)

        inventory_tag.sort(key=lambda entry: int(entry.get("Slot", Byte(0))))
        self.refresh_views(select_path=(tag_name,))

    def _find_inventory_item(
        self,
        inventory_tag: NbtList,
        slot: int,
        exclude: Optional[Compound] = None,
    ) -> Optional[Compound]:
        for item in inventory_tag:
            if item is exclude:
                continue
            if int(item.get("Slot", Byte(0))) == slot:
                return item
        return None


def main() -> None:
    app = NBTEditorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
