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
        
        if fresco_xyz.renderer:
            cfg = fresco_xyz.renderer.PLATE_CONFIG
            self.plate_rows = cfg['rows']
            self.plate_cols = cfg['cols']
            self.well_spacing_mm = cfg['well_spacing']
            self.well_step = int(self.well_spacing_mm * 200)
        else:
            self.plate_rows = 8
            self.plate_cols = 12
            self.well_spacing_mm = 9.0
            self.well_step = 1800
        
        self.plate_size_96 = (self.plate_cols, self.plate_rows)

    def perform(self):
        pass

    def hold_position(self, seconds):
        time.sleep(seconds)
