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
        else:
            self.plate_rows = 8
            self.plate_cols = 12
            self.well_spacing_mm = 9.0
            self.well_spacing_steps = 1800
        
        self.plate_size_96 = (self.plate_cols, self.plate_rows)

    def perform(self):
        pass

    def hold_position(self, seconds):
        time.sleep(seconds)
        self.check_pause_stop()

    def check_pause_stop(self):
        """Check if protocol should pause or stop."""
        if self.protocol_controller:
            while self.protocol_controller.protocol_paused:
                time.sleep(0.1)
            if self.protocol_controller.protocol_stop_requested:
                raise InterruptedError("Protocol stopped by user")

    def get_well_position(self, row: int, col: int, z: int = None):
        """
        Helper: Get plate-relative position (in steps) for a specific well.
        Convenient for well-based protocols.

        Args:
            row: Row index (0-based, 0 = A, 1 = B, etc.)
            col: Column index (0-based, 0 = first column)
            z: Optional z position in steps (if None, keeps current z)

        Returns:
            tuple: (x_steps, y_steps, z_steps) for use with set_position()
        """
        x_steps = col * self.well_spacing_steps
        y_steps = row * self.well_spacing_steps

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
