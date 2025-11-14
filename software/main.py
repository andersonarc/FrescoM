from tkinter import Tk
from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.fresco_camera import BaseCamera
from services.fresco_renderer import FrescoRenderer
from services.image_processor import ImageProcessor
from ui.fresco_ui import MainUI
from plates import get_available_plate_types
import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    
    parser.add_argument(
        '--plate-type',
        type=str,
        default='96-well',
        choices=get_available_plate_types(),
        help='Microplate type to use (default: 96-well)'
    )
    
    parser.add_argument(
        '--virtual',
        action='store_true',
        help='Run in virtual-only mode'
    )
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    print(f"Starting FrescoM with {args.plate_type} plate")
    print(f"Mode: {'Virtual' if args.virtual else 'Hardware'}")

    # Initialize components
    fresco_xyz = FrescoXYZ(virtual_only=args.virtual, plate_type=args.plate_type)
    image_processor = ImageProcessor()
    fresco_renderer = FrescoRenderer(image_processor, fresco_xyz, plate_type=args.plate_type)
    
    # Link renderer to xyz for collision detection
    fresco_xyz.renderer = fresco_renderer
    
    z_camera = ZCamera(None if args.virtual else BaseCamera(), fresco_renderer)
    
    # Create UI
    root = Tk()
    root.geometry("1400x900")
    
    MainUI(
        fresco_xyz=fresco_xyz,
        z_camera=z_camera,
        fresco_camera=None if args.virtual else BaseCamera(),
        fresco_renderer=fresco_renderer,
        virtual_only=args.virtual
    )
    
    root.mainloop()


if __name__ == '__main__':
    main()
