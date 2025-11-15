from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.images_storage import ImagesStorage
from os import listdir
from os.path import isfile, join
from services.fresco_calss_loader import FrescoClassLoader
from services.protocols.base_protocol import BaseProtocol
import logging


class ProtocolsPerformer:

    def __init__(self,
                 fresco_xyz: FrescoXYZ,
                 z_camera: ZCamera,
                 images_storage: ImagesStorage):
        self.fresco_xyz = fresco_xyz
        self.z_camera = z_camera
        self.images_storage = images_storage
        self.protocols_folder_path = './services/protocols'
        self.class_loader = FrescoClassLoader()
        self.current_protocol: BaseProtocol = None

    def available_protocols(self):
        files = [self.protocols_folder_path + '/' + f for f in listdir(self.protocols_folder_path) 
                if isfile(join(self.protocols_folder_path, f)) and f.endswith('.py') and f != '__init__.py']
        return sorted(files)

    def perform_protocol(self, path: str, time_scale: float = 1.0):
        """Load and execute a protocol from file.

        Args:
            path: Path to protocol file
            time_scale: Time scale multiplier (0.1=10x faster, 1.0=real-time, 2.0=2x slower)
        """
        logging.info(f'Loading protocol from: {path}')

        # Reset stop flag before starting
        self.fresco_xyz.reset_stop_flag()

        try:
            protocol_class = self.class_loader.import_class(path)
            self.current_protocol = protocol_class(self.fresco_xyz, self.z_camera, self.images_storage)
            self.current_protocol.time_scale = time_scale

            logging.info(f'Executing protocol: {protocol_class.__name__} (time_scale={time_scale}x)')
            self.current_protocol.perform()
            
            if self.fresco_xyz.should_stop():
                logging.info('Protocol stopped by user request')
            else:
                logging.info('Protocol completed successfully')
                
        except Exception as e:
            logging.error(f'Protocol execution failed: {e}')
            raise
        finally:
            self.current_protocol = None
