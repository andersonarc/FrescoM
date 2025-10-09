from services.fresco_camera import DummyCamera, FrescoCamera
from services.fresco_renderer import FrescoRenderer
from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.image_processor import ImageProcessor
from ui.fresco_ui import MainUI
from tkinter import BOTH, Tk, Scrollbar
from tkinter.ttk import Frame, Label
import argparse

def main():
    # Use commandline arguments to check if we're running in without the actual robot present
    parser = argparse.ArgumentParser()
    parser.add_argument('--virtual_only', action='store_true')
    args = parser.parse_args()

    # Instantiate the necessary classes
    fresco_xyz = FrescoXYZ(args.virtual_only)
    image_processor = ImageProcessor()
    fresco_camera = DummyCamera() if args.virtual_only else FrescoCamera(image_processor)
    fresco_renderer = FrescoRenderer(image_processor, fresco_xyz)
    z_camera = ZCamera(fresco_xyz, fresco_camera)

    # Create and run the GUI
    root = Tk()
    root.geometry("1800x1200+300+300")
    app = MainUI(fresco_xyz, z_camera, fresco_camera, fresco_renderer, args.virtual_only)
    root.mainloop()


if __name__ == '__main__':
    main()
