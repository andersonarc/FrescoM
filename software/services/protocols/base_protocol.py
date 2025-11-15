from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.images_storage import ImagesStorage
import time


class BaseProtocol:

    def __init__(self,
                 fresco_xyz: FrescoXYZ,
                 z_camera: ZCamera,
                 images_storage: ImagesStorage):
        self.fresco_xyz = fresco_xyz
        self.z_camera = z_camera
        self.images_storage = images_storage
        self.protocol_controller = None

        if fresco_xyz.renderer:
            cfg = fresco_xyz.renderer.plate_config
            self.plate_rows = cfg['rows']
            self.plate_cols = cfg['cols']
            self.well_spacing_mm = cfg['well_spacing']
            self.well_spacing_steps = int(self.well_spacing_mm * 200)
            self.corner_offset_x_steps = int(cfg['corner_offset_x'] * 200)
            self.corner_offset_y_steps = int(cfg['corner_offset_y'] * 200)
        else:
            self.plate_rows = 8
            self.plate_cols = 12
            self.well_spacing_mm = 9.0
            self.well_spacing_steps = 1800
            self.corner_offset_x_steps = int(14.38 * 200)  # 96-well default
            self.corner_offset_y_steps = int(11.24 * 200)
        
        self.plate_size_96 = (self.plate_cols, self.plate_rows)
        self.time_scale = 1.0  # Default: real-time (1.0x speed)

    def perform(self):
        pass

    def sleep(self, seconds):
        """
        Sleep for specified seconds, scaled by time_scale.
        Use this instead of time.sleep() for protocol timing.

        Args:
            seconds: Duration to sleep in seconds (will be scaled)
        """
        # Read time scale from UI in real-time if available (allows runtime changes)
        try:
            if self.fresco_xyz.time_scale_var is not None:
                time_scale = self.fresco_xyz.time_scale_var.get()
            else:
                time_scale = self.time_scale
        except:
            time_scale = self.time_scale

        actual_seconds = seconds * time_scale
        if actual_seconds > 0:
            time.sleep(actual_seconds)
        self.check_pause_stop()

    def hold_position(self, seconds):
        self.sleep(seconds)

    def check_pause_stop(self):
        if self.protocol_controller:
            while self.protocol_controller.protocol_paused:
                time.sleep(0.1)
            if self.protocol_controller.protocol_stop_requested:
                raise InterruptedError("Protocol stopped by user")

    def get_well_position(self, row: int, col: int, z: int = None):
        """
        Helper: Get position (in steps) for a specific well center.
        Position is relative to plate corner (0,0).

        Args:
            row: Row index (0-based, 0 = A, 1 = B, etc.)
            col: Column index (0-based, 0 = first column)
            z: Optional z position in steps (if None, keeps current z)

        Returns:
            tuple: (x_steps, y_steps, z_steps) for use with set_position()
        """
        x_steps = self.corner_offset_x_steps + col * self.well_spacing_steps
        y_steps = self.corner_offset_y_steps + row * self.well_spacing_steps

        if z is None:
            z_steps = self.fresco_xyz.virtual_position['z']
        else:
            z_steps = z

        return (int(x_steps), int(y_steps), int(z_steps))

    def move_to_well(self, row: int, col: int, z: int = None):
        """
        Helper: Move to a specific well.
        Convenient for well-based protocols.

        Args:
            row: Row index (0-based, 0 = A, 1 = B, etc.)
            col: Column index (0-based, 0 = first column)
            z: Optional z position in steps (if None, keeps current z)
        """
        x, y, z = self.get_well_position(row, col, z)
        self.fresco_xyz.set_position(x, y, z)

    def parse_well_label(self, well_label: str):
        """
        Parse well label (e.g., "A1", "B12") into row and column indices.

        Args:
            well_label: Well label string (e.g., "A1", "B12", "P24")

        Returns:
            tuple: (row, col) as 0-based indices

        Raises:
            ValueError: If label is invalid
        """
        import re
        match = re.match(r'^([A-Z]+)(\d+)$', well_label.upper())
        if not match:
            raise ValueError(f"Invalid well label: {well_label}")

        row_label = match.group(1)
        col_str = match.group(2)

        # Convert row letter to index (A=0, B=1, etc.)
        row = ord(row_label) - ord('A')
        col = int(col_str) - 1

        if row < 0 or row >= self.plate_rows:
            raise ValueError(f"Row '{row_label}' out of range (max {chr(ord('A') + self.plate_rows - 1)})")
        if col < 0 or col >= self.plate_cols:
            raise ValueError(f"Column {col_str} out of range (max {self.plate_cols})")

        return (row, col)

    def move_to_well_label(self, well_label: str, z: int = None):
        """
        Move to a well specified by label (e.g., "A1", "B12").

        Args:
            well_label: Well label string (e.g., "A1", "B12", "P24")
            z: Optional z position in steps (if None, keeps current z)
        """
        row, col = self.parse_well_label(well_label)
        self.move_to_well(row, col, z)
