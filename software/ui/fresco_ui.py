from tkinter import BOTH, Tk
import tkinter as tk
from tkinter.ttk import Frame, Label
from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.fresco_camera import BaseCamera
from services.fresco_renderer import FrescoRenderer
from services.protocols_performer import ProtocolsPerformer
from services.images_storage import ImagesStorage
from PIL import Image, ImageTk
from tkinter import Toplevel

from ui.steps_manual_controller_ui import StepsManualController
from ui.macro_steps_manual_controller_ui import MacroStepsManualController
from ui.initialization_ui import Initialization
from ui.auto_focus_ui import AutoFocus
from ui.functions_ui import Functions
from ui.serial_connection_ui import SerialConnectionView


class MainUI(Frame):

    def __init__(self,
                 fresco_xyz: FrescoXYZ,
                 z_camera: ZCamera,
                 fresco_camera: BaseCamera,
                 fresco_renderer: FrescoRenderer,
                 virtual_only: bool):
        super().__init__()
        self.fresco_xyz = fresco_xyz
        self.z_camera = z_camera
        self.fresco_camera = fresco_camera
        self.fresco_renderer = fresco_renderer
        self.virtual_only = virtual_only
        self.camera = self.fresco_renderer if self.virtual_only else self.fresco_camera
        self.image_label = None

        self.init_ui()

    def init_ui(self):
        self.master.title("Fresco Labs")
        self.pack(fill=BOTH, expand=1)

        # Manual controls
        steps_manual_controller = StepsManualController(self, fresco_xyz=self.fresco_xyz)
        steps_manual_controller.place(x=0, y=0)

        macro_steps_controller = MacroStepsManualController(self, fresco_xyz=self.fresco_xyz)
        macro_steps_controller.place(x=0, y=130)

        initialization_controller = Initialization(self, fresco_xyz=self.fresco_xyz)
        initialization_controller.place(x=0, y=340)

        auto_focus_controller = AutoFocus(self, fresco_xyz=self.fresco_xyz, z_camera=self.z_camera)
        auto_focus_controller.place(x=0, y=460)

        # Functions and protocols
        images_storage = ImagesStorage()
        protocols_performer = ProtocolsPerformer(fresco_xyz=self.fresco_xyz,
                                                z_camera=self.z_camera,
                                                images_storage=images_storage)
        functions_controller = Functions(self,
                                        fresco_xyz=self.fresco_xyz,
                                        z_camera=self.z_camera,
                                        protocols_performer=protocols_performer,
                                        images_storage=images_storage)
        functions_controller.place(x=0, y=560)

        # Top buttons
        serial_port_control_button = tk.Button(self, text='Serial Port', command=self.open_serial_connection_ui)
        serial_port_control_button.place(x=300, y=0)

        if not self.virtual_only:
            toggle_button = tk.Button(self, text='Switch View', command=self.switch_view)
            toggle_button.place(x=380, y=0)

        # Camera view
        image_array = self.camera.get_current_image()
        camera_image = ImageTk.PhotoImage(image=Image.fromarray(image_array).resize((800, 800), Image.ANTIALIAS))
        self.image_label = Label(self, image=camera_image)
        self.image_label.image = camera_image
        self.image_label.place(x=300, y=30)

        # Keyboard controls for 3D view
        self.master.bind('<Key>', self.handle_keypress)

        self.after(100, self.update_image)

    def switch_view(self):
        """Toggle between real camera and virtual renderer."""
        if not self.virtual_only:
            if self.camera == self.fresco_camera:
                self.camera = self.fresco_renderer
            else:
                self.camera = self.fresco_camera

    def update_image(self):
        image_array = self.camera.get_current_image()
        camera_image = ImageTk.PhotoImage(image=Image.fromarray(image_array).resize((800, 800), Image.ANTIALIAS))
        self.image_label.configure(image=camera_image)
        self.image_label.image = camera_image

        # Adaptive update rate
        if hasattr(self.camera, 'should_update_frequently'):
            update_delay = 100 if self.camera.should_update_frequently() else 500
        else:
            update_delay = 100

        self.after(update_delay, self.update_image)

    def handle_keypress(self, event):
        """Handle keyboard controls for 3D renderer."""
        if self.camera != self.fresco_renderer:
            return
        
        key = event.char.lower()

        if key == '+':
            self.fresco_renderer.zoom_in()
        elif key == '-':
            self.fresco_renderer.zoom_out()
        elif key == 'a':
            self.fresco_renderer.rotate_left()
        elif key == 'd':
            self.fresco_renderer.rotate_right()
        elif key == 'w':
            self.fresco_renderer.rotate_up()
        elif key == 's':
            self.fresco_renderer.rotate_down()
        elif key == 'c':
            self.fresco_renderer.center_on_robot()
        elif key == 'r':
            self.fresco_renderer.reset_view()

    def open_serial_connection_ui(self):
        new_window = Toplevel(self)
        new_window.title("Serial Connection")
        new_window.geometry("400x250")
        SerialConnectionView(new_window).pack()
