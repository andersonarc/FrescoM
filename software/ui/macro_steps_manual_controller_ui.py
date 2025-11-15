import tkinter as tk
from tkinter.ttk import Frame
from tkinter import messagebox
from services.fresco_xyz import FrescoXYZ
import _thread


class MacroStepsManualController(Frame):

    def __init__(self, master, fresco_xyz: FrescoXYZ):
        super().__init__(master=master, height=240, width=500)
        self.fresco_xyz = fresco_xyz
        self.number_of_steps_entry: tk.Entry = None
        self.well_label_entry: tk.Entry = None
        self.init_ui()

    def init_ui(self):
        x_macro_up_button = tk.Button(self, text="↑↑", command=self.move_x_macro_up)
        x_macro_up_button.grid(row=1, column=1)

        x_macro_down_button = tk.Button(self, text="↓↓", command=self.move_x_macro_down)
        x_macro_down_button.grid(row=3, column=1)

        y_macro_left_button = tk.Button(self, text="←←", command=self.move_y_macro_left)
        y_macro_left_button.grid(row=2, column=0)

        y_macro_right_button = tk.Button(self, text="→→", command=self.move_y_macro_right)
        y_macro_right_button.grid(row=2, column=2)

        z_up_button = tk.Button(self, text="↑↑", command=self.move_z_macro_up)
        z_up_button.grid(row=1, column=3)

        z_down_button = tk.Button(self, text="↓↓", command=self.move_z_macro_down)
        z_down_button.grid(row=3, column=3)

        manifold_up_button = tk.Button(self, text="↑↑", command=self.move_manifold_up)
        manifold_up_button.grid(row=1, column=4)

        manifold_down_button = tk.Button(self, text="↓↓", command=self.move_manifold_down)
        manifold_down_button.grid(row=3, column=4)

        self.number_of_steps_entry = tk.Entry(self)
        self.number_of_steps_entry.grid(sticky=tk.W, row=4, column=0, columnspan=4)
        # Default to well spacing for current plate type
        default_steps = str(self.fresco_xyz.plate.get('steps_per_well', 1800))
        self.number_of_steps_entry.insert(tk.END, default_steps)

        go_to_zero_button = tk.Button(self, text='Go to zero ZXY', command=self.go_to_zero)
        go_to_zero_button.grid(sticky=tk.W, row=5, column=0, columnspan=4)

        go_to_zero_manifold = tk.Button(self, text='Go to zero Manifold', command=self.go_to_zero_manifold)
        go_to_zero_manifold.grid(sticky=tk.W, row=6, column=0, columnspan=4)

        go_to_zero_z_button = tk.Button(self, text='Go to zero Z', command=self.go_to_zero_z)
        go_to_zero_z_button.grid(sticky=tk.W, row=7, column=0, columnspan=4)

        # Go to well entry and button
        well_label = tk.Label(self, text="Well:")
        well_label.grid(sticky=tk.W, row=8, column=0)

        self.well_label_entry = tk.Entry(self, width=10)
        self.well_label_entry.grid(sticky=tk.W, row=8, column=1, columnspan=2)
        self.well_label_entry.insert(tk.END, "A1")

        go_to_well_button = tk.Button(self, text='Go to well', command=self.go_to_well)
        go_to_well_button.grid(sticky=tk.W, row=8, column=3, columnspan=2)

    def current_step_size(self) -> int:
        return int(self.number_of_steps_entry.get())

    def move_x_macro_up(self):
        _thread.start_new_thread(self.fresco_xyz.delta, (self.current_step_size(), 0, 0))

    def move_x_macro_down(self):
        _thread.start_new_thread(self.fresco_xyz.delta, (-1 * self.current_step_size(), 0, 0))

    def move_y_macro_left(self):
        _thread.start_new_thread(self.fresco_xyz.delta, (0, self.current_step_size(), 0))

    def move_y_macro_right(self):
        _thread.start_new_thread(self.fresco_xyz.delta, (0,  -1 * self.current_step_size(), 0))

    def move_z_macro_up(self):
        _thread.start_new_thread(self.fresco_xyz.delta, (0, 0,  -1 * self.current_step_size()))

    def move_z_macro_down(self):
        _thread.start_new_thread(self.fresco_xyz.delta, (0, 0, self.current_step_size()))

    def go_to_zero(self):
        _thread.start_new_thread(self.fresco_xyz.go_to_zero, ())

    def go_to_zero_manifold(self):
        _thread.start_new_thread(self.fresco_xyz.go_to_zero_manifold, ())

    def go_to_zero_z(self):
        _thread.start_new_thread(self.fresco_xyz.go_to_zero_z, ())

    def move_manifold_up(self):
        _thread.start_new_thread(self.fresco_xyz.manifold_delta, (-1 * self.current_step_size(),))

    def move_manifold_down(self):
        _thread.start_new_thread(self.fresco_xyz.manifold_delta, (self.current_step_size(),))

    def go_to_well(self):
        well_label = self.well_label_entry.get().strip().upper()
        try:
            # Parse well label (e.g., "A1" -> row=0, col=0)
            import re
            match = re.match(r'^([A-Z]+)(\d+)$', well_label)
            if not match:
                raise ValueError(f"Invalid well label: {well_label}")

            row_letter = match.group(1)
            col_num = int(match.group(2))

            # Convert to indices
            row = ord(row_letter) - ord('A')
            col = col_num - 1

            # Get plate config
            cfg = self.fresco_xyz.plate
            if not cfg:
                messagebox.showerror("Error", "No plate configured")
                return

            # Validate indices
            plate_rows = cfg.get('rows', 8)
            plate_cols = cfg.get('cols', 12)
            if row < 0 or row >= plate_rows or col < 0 or col >= plate_cols:
                messagebox.showerror("Error", f"Well {well_label} out of range")
                return

            # Calculate position from plate corner
            well_spacing = cfg.get('steps_per_well', 1800)
            corner_offset_x = int(cfg.get('corner_offset_x', 14.38) * 200)
            corner_offset_y = int(cfg.get('corner_offset_y', 11.24) * 200)

            x = corner_offset_x + col * well_spacing
            y = corner_offset_y + row * well_spacing
            z = self.fresco_xyz.virtual_position['z']

            # Move to well
            _thread.start_new_thread(self.fresco_xyz.set_position, (x, y, z))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to go to well: {e}")

