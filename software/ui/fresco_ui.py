from tkinter import BOTH, Tk
import tkinter as tk
from tkinter.ttk import Frame, Label, Notebook
from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.fresco_camera import BaseCamera
from services.fresco_renderer import FrescoRenderer
from services.protocols_performer import ProtocolsPerformer
from services.images_storage import ImagesStorage
from ui.stdout_view import StdoutView, StdoutCapture
from PIL import Image, ImageTk
from tkinter import Toplevel
import sys
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ui.steps_manual_controller_ui import StepsManualController
from ui.macro_steps_manual_controller_ui import MacroStepsManualController
from ui.initialization_ui import Initialization
from ui.auto_focus_ui import AutoFocus
from ui.functions_ui import Functions
from ui.serial_connection_ui import SerialConnectionView
from ui.protocols_performer_ui import ProtocolsPerformerUI
from ui.ai_protocol_generator_ui import AIProtocolGeneratorUI


class PumpTraceView(tk.Frame):
    def __init__(self, master, fresco_renderer):
        super().__init__(master)
        self.renderer = fresco_renderer
        
        self.fig = Figure(figsize=(4, 10), dpi=80)
        self.axes = []
        
        for i in range(8):
            ax = self.fig.add_subplot(8, 1, i+1)
            ax.set_ylabel(f'P{i}', rotation=0, labelpad=15, fontsize=9)
            ax.grid(True, alpha=0.3, linestyle=':')
            ax.tick_params(labelsize=7)
            if i < 7:
                ax.set_xticklabels([])
            self.axes.append(ax)
        
        self.axes[7].set_xlabel('Event Sequence', fontsize=8)
        self.fig.tight_layout(pad=0.5, h_pad=0.3)
        
        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        control_frame = tk.Frame(self)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(control_frame, text="Auto", variable=self.auto_var).pack(side=tk.LEFT, padx=5)
        
        self.sync_var = tk.BooleanVar(value=True)
        tk.Checkbutton(control_frame, text="Sync", variable=self.sync_var).pack(side=tk.LEFT, padx=5)
        
        tk.Label(control_frame, text="Well:").pack(side=tk.LEFT)
        self.well_entry = tk.Entry(control_frame, width=6)
        self.well_entry.pack(side=tk.LEFT, padx=5)
        self.well_entry.bind('<Return>', lambda e: self.update_plot())
        
        self.current_well = None
        self.after(50, self.update_loop)
    
    def update_loop(self):
        self.update_plot()
        self.after(50, self.update_loop)
    
    def update_plot(self):
        if self.auto_var.get() and self.renderer.current_well:
            well_label = self.renderer.current_well.label
        else:
            well_label = self.well_entry.get().upper()
            if not well_label:
                return
        
        self.current_well = well_label
        
        well = None
        for w in self.renderer.wells:
            if w.label == well_label:
                well = w
                break
        
        if not well:
            return
        
        if self.sync_var.get():
            pump_data = self._build_synchronized_traces(well)
        else:
            pump_data = self._build_independent_traces(well)
        
        for pump_idx in range(8):
            ax = self.axes[pump_idx]
            ax.clear()
            
            data = pump_data[pump_idx]
            if data['x']:
                ax.plot(data['x'], data['y'], 'k-', linewidth=1.5)
                
                for idx in data['interruptions']:
                    if idx < len(data['x']):
                        ax.axvline(x=data['x'][idx], color='red', linestyle='--', 
                                  linewidth=1, alpha=0.7)
            
            ax.set_ylabel(f'P{pump_idx}', rotation=0, labelpad=15, fontsize=9)
            ax.grid(True, alpha=0.3, linestyle=':')
            ax.tick_params(labelsize=7)
            
            if pump_idx < 7:
                ax.set_xticklabels([])
        
        self.axes[7].set_xlabel('Event Sequence', fontsize=8)
        self.fig.suptitle(f'Well {well_label}', fontsize=10, fontweight='bold')
        self.canvas.draw()
    
    def _build_synchronized_traces(self, well):
        pump_data = {}
        for i in range(8):
            pump_data[i] = {'x': [], 'y': [], 'interruptions': []}
        
        cumulative = [0] * 8
        last_timestamp = None
        
        for event_seq, (timestamp, pump_idx, delta) in enumerate(well.pump_events):
            if last_timestamp and (timestamp - last_timestamp) > 5.0:
                for p in range(8):
                    pump_data[p]['interruptions'].append(event_seq)
            
            cumulative[pump_idx] += delta
            
            for p in range(8):
                pump_data[p]['x'].append(event_seq)
                pump_data[p]['y'].append(cumulative[p])
            
            last_timestamp = timestamp
        
        return pump_data
    
    def _build_independent_traces(self, well):
        pump_data = {}
        for i in range(8):
            pump_data[i] = {'x': [], 'y': [], 'interruptions': []}
        
        cumulative = [0] * 8
        event_seq = 0
        last_timestamp = None
        
        for timestamp, pump_idx, delta in well.pump_events:
            if last_timestamp and (timestamp - last_timestamp) > 5.0:
                pump_data[pump_idx]['interruptions'].append(len(pump_data[pump_idx]['x']))
            
            cumulative[pump_idx] += delta
            pump_data[pump_idx]['x'].append(event_seq)
            pump_data[pump_idx]['y'].append(cumulative[pump_idx])
            event_seq += 1
            last_timestamp = timestamp
        
        return pump_data


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
        
        self.stdout_view = StdoutView()
        self.stdout_capture = StdoutCapture(self.stdout_view.add_text)
        
        self.view_modes = ['renderer', 'camera', 'stdout']
        self.current_view_index = 0
        
        if self.virtual_only:
            self.view_modes = ['renderer', 'stdout']
        
        self.camera = self.fresco_renderer
        self.image_label = None

        self.init_ui()
        
        sys.stdout = self.stdout_capture
        sys.stderr = self.stdout_capture

    def init_ui(self):
        self.master.title("Fresco Labs")
        self.pack(fill=BOTH, expand=1)

        main_content = Frame(self)
        main_content.pack(side=tk.RIGHT, fill=BOTH, expand=True)

        camera_frame = Frame(main_content)
        camera_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        btn_row = Frame(camera_frame)
        btn_row.pack(fill=tk.X, pady=(0, 5))
        
        tk.Button(btn_row, text='Serial Port', command=self.open_serial_connection_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_row, text='Change View', command=self.cycle_view).pack(side=tk.LEFT, padx=2)
        
        self.view_label = tk.Label(btn_row, text=f"View: {self.view_modes[self.current_view_index]}", 
                                   font=("Arial", 9, "bold"))
        self.view_label.pack(side=tk.LEFT, padx=10)
        
        tk.Label(btn_row, text="3D: +/- zoom, WASD rotate, C center, R reset",
                font=("Arial", 8), fg="gray").pack(side=tk.RIGHT, padx=5)
        
        image_array = self.camera.get_current_image()
        camera_image = ImageTk.PhotoImage(image=Image.fromarray(image_array).resize((800, 800), Image.ANTIALIAS))
        self.image_label = Label(camera_frame, image=camera_image)
        self.image_label.image = camera_image
        self.image_label.pack()

        pump_panel = PumpTraceView(main_content, self.fresco_renderer)
        pump_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        control_notebook = Notebook(self)
        control_notebook.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        main_tab = Frame(control_notebook)
        control_notebook.add(main_tab, text="Controls")
        
        steps_manual_controller = StepsManualController(main_tab, fresco_xyz=self.fresco_xyz)
        steps_manual_controller.pack(pady=5)

        macro_steps_controller = MacroStepsManualController(main_tab, fresco_xyz=self.fresco_xyz)
        macro_steps_controller.pack(pady=5)

        initialization_controller = Initialization(main_tab, fresco_xyz=self.fresco_xyz)
        initialization_controller.pack(pady=5)

        auto_focus_controller = AutoFocus(main_tab, fresco_xyz=self.fresco_xyz, z_camera=self.z_camera)
        auto_focus_controller.pack(pady=5)

        protocols_tab = Frame(control_notebook)
        control_notebook.add(protocols_tab, text="Protocols")
        
        images_storage = ImagesStorage()
        protocols_performer = ProtocolsPerformer(fresco_xyz=self.fresco_xyz,
                                                z_camera=self.z_camera,
                                                images_storage=images_storage)
        
        functions_controller = Functions(protocols_tab,
                                        fresco_xyz=self.fresco_xyz,
                                        z_camera=self.z_camera,
                                        protocols_performer=protocols_performer,
                                        images_storage=images_storage)
        functions_controller.pack(pady=5)
        
        tk.Button(protocols_tab, text="Open Protocol Manager", 
                 command=lambda: self.open_protocol_manager(protocols_performer)).pack(pady=10)
        
        ai_tab = Frame(control_notebook)
        control_notebook.add(ai_tab, text="AI Generator")
        
        tk.Button(ai_tab, text="Open Protocol Generator",
                 command=lambda: self.open_ai_generator(protocols_performer),
                 font=("Arial", 10, "bold"), padx=20, pady=10).pack(pady=20)
        
        tk.Label(ai_tab, text="Generate protocols using AI\nfrom natural language descriptions",
                font=("Arial", 9), fg="gray", wraplength=250, justify=tk.CENTER).pack(pady=10)

        self.master.bind('<Key>', self.handle_keypress)

        self.after(100, self.update_image)

    def cycle_view(self):
        self.current_view_index = (self.current_view_index + 1) % len(self.view_modes)
        mode = self.view_modes[self.current_view_index]
        
        if mode == 'renderer':
            self.camera = self.fresco_renderer
        elif mode == 'camera':
            self.camera = self.fresco_camera
        elif mode == 'stdout':
            self.camera = self.stdout_view
        
        self.view_label.config(text=f"View: {mode}")

    def update_image(self):
        image_array = self.camera.get_current_image()
        camera_image = ImageTk.PhotoImage(image=Image.fromarray(image_array).resize((800, 800), Image.ANTIALIAS))
        self.image_label.configure(image=camera_image)
        self.image_label.image = camera_image

        if hasattr(self.camera, 'should_update_frequently'):
            update_delay = 100 if self.camera.should_update_frequently() else 500
        else:
            update_delay = 100

        self.after(update_delay, self.update_image)

    def handle_keypress(self, event):
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
    
    def open_protocol_manager(self, protocols_performer):
        window = Toplevel(self)
        window.title("Protocol Manager")
        ProtocolsPerformerUI(window, protocols_performer).pack(fill=BOTH, expand=True)
    
    def open_ai_generator(self, protocols_performer):
        window = Toplevel(self)
        window.title("Protocol Generator")
        window.geometry("900x850")
        AIProtocolGeneratorUI(window, protocols_performer).pack(fill=BOTH, expand=True)
