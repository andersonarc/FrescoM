import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np
import logging
import threading
from plates import get_plate_config, STEPS_PER_MM


class Well:
    def __init__(self, row, col, center_x, center_y, radius, depth, label):
        self.row = row
        self.col = col
        self.label = label
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        self.depth = depth
        self.capture_size = radius * 1.5
        self.pump_events = []
    
    def contains_point(self, x, y):
        return (abs(x - self.center_x) <= self.capture_size and 
                abs(y - self.center_y) <= self.capture_size)
    
    def add_pump_event(self, pump_index, volume):
        import time
        self.pump_events.append((time.time(), pump_index, volume))


class FrescoRenderer:
    MANIFOLD_TIP_LENGTH = 20.0
    WELL_SEGMENTS = 12
    TRAJECTORY_MAX_POINTS = 500
    
    def __init__(self, image_processor, fresco_xyz, plate_type='96-well'):
        self.image_processor = image_processor
        self.fresco_xyz = fresco_xyz
        self.plate_type = plate_type
        self.plate_config = get_plate_config(plate_type)
        
        self.width = 800
        self.height = 800
        
        cfg = self.plate_config
        self.plate_width = (cfg['cols'] - 1) * cfg['well_spacing']
        self.plate_height = (cfg['rows'] - 1) * cfg['well_spacing']
        
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height), OPENGL | HIDDEN)
        pygame.display.set_caption("Fresco 3D View")
        
        pygame.font.init()

        # Scale robot and labels based on plate type
        base_well_spacing = 9.0  # 96-well plate
        scale_factor = cfg['well_spacing'] / base_well_spacing
        # More aggressive scaling for labels to prevent overlap on dense plates
        font_size = max(6, int(24 * (scale_factor ** 1.5)))
        self.label_font = pygame.font.SysFont('Arial', font_size, bold=True)
        self.robot_scale = scale_factor
        self.label_scale = 10.0 * scale_factor  # Scale OpenGL text labels
        self.label_offset = 8.0 * scale_factor  # Distance from plate edge to labels

        self._init_opengl()

        self.camera_distance = 250.0
        self.camera_elevation = 30.0
        self.camera_azimuth = 45.0
        self.zoom_level = 1.0
        self.target_position = {'x': self.plate_width / 2, 'y': self.plate_height / 2, 'z': 0.0}

        self.wells = self._create_wells()
        self.current_well = None

        self.position_history = []
        self.position_lock = threading.Lock()
        self.frame_count = 0
        self.last_render_pos = None
        self.is_moving = False
        self.collision_state = False
        self.cached_image = None
        self.main_thread_id = threading.get_ident()

        self.pump_colors = [
            (1.0, 0.3, 0.3), (0.3, 1.0, 0.3), (0.3, 0.3, 1.0), (1.0, 1.0, 0.3),
            (1.0, 0.3, 1.0), (0.3, 1.0, 1.0), (1.0, 0.6, 0.3), (0.6, 0.3, 1.0),
        ]

        self.camera_flash = False  # Camera flash effect (yellow for 1 frame)

        logging.info(f"Renderer initialized with {plate_type} plate")
    
    def _init_opengl(self):
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0.95, 0.95, 0.95, 1.0)
        
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, self.width / self.height, 1.0, 1000.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
    
    def _create_wells(self):
        cfg = self.plate_config
        wells = []

        well_radius = cfg['well_diameter'] / 2

        for row in range(cfg['rows']):
            for col in range(cfg['cols']):
                x = col * cfg['well_spacing']
                y = row * cfg['well_spacing']
                label = f"{cfg['row_labels'][row]}{col + 1}"
                well = Well(row, col, x, y, well_radius, cfg['well_depth'], label)
                wells.append(well)

        return wells

    def clear_position_history(self):
        with self.position_lock:
            self.position_history = []
            logging.info("Position history cleared due to plate calibration change")

    def record_position(self, x_mm, y_mm, z_mm):
        # Robot position is recorded in absolute coordinates (not transformed by plate offset)
        # The plate wells will be drawn at positions adjusted by the offset
        pos = {'x': self.plate_width - x_mm, 'y': self.plate_height - y_mm, 'z': z_mm}
        with self.position_lock:
            if (not self.position_history or
                abs(pos['x'] - self.position_history[-1]['x']) > 0.001 or
                abs(pos['y'] - self.position_history[-1]['y']) > 0.001 or
                abs(pos['z'] - self.position_history[-1]['z']) > 0.001):
                self.position_history.append(pos)
                if len(self.position_history) > self.TRAJECTORY_MAX_POINTS:
                    self.position_history.pop(0)

    def get_well_at_position(self, x_mm, y_mm):
        # Convert robot absolute position to plate-relative position
        # Wells are in plate-relative coordinates (0 to plate_width)
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'plate'):
            plate_offset_x = self.fresco_xyz.plate['bottom_left'][0] / STEPS_PER_MM
            plate_offset_y = self.fresco_xyz.plate['bottom_left'][1] / STEPS_PER_MM
            plate_relative_x = x_mm - plate_offset_x
            plate_relative_y = y_mm - plate_offset_y
        else:
            plate_relative_x = x_mm
            plate_relative_y = y_mm

        for well in self.wells:
            if well.contains_point(plate_relative_x, plate_relative_y):
                return well
        return None
    
    def record_pump_event(self, pump_index, volume):
        if self.current_well:
            self.current_well.add_pump_event(pump_index, volume)
            logging.info(f"Pump event recorded: Well {self.current_well.label}, Pump {pump_index}, Volume {volume}")
    
    def get_current_image(self):
        # OpenGL can ONLY be called from the main thread
        # If called from another thread (e.g. focus), return cached image
        if threading.get_ident() != self.main_thread_id:
            if self.cached_image is not None:
                return self.cached_image
            # No cached image yet, return black
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Clear any previous OpenGL errors
        while glGetError() != GL_NO_ERROR:
            pass

        robot_pos_physical = self._get_robot_position_physical()
        robot_pos = self._get_robot_position()
        self.current_well = self.get_well_at_position(robot_pos_physical['x'], robot_pos_physical['y'])

        led_color = self._get_led_color()
        self._update_position_history(robot_pos)

        try:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            camera_x = self.target_position['x'] + self.camera_distance * np.cos(np.radians(self.camera_elevation)) * np.sin(np.radians(self.camera_azimuth))
            camera_y = self.target_position['y'] + self.camera_distance * np.cos(np.radians(self.camera_elevation)) * np.cos(np.radians(self.camera_azimuth))
            camera_z = self.target_position['z'] + self.camera_distance * np.sin(np.radians(self.camera_elevation))

            gluLookAt(
                camera_x / self.zoom_level, camera_y / self.zoom_level, camera_z / self.zoom_level,
                self.target_position['x'], self.target_position['y'], self.target_position['z'],
                0, 0, 1
            )

            self._draw_scene(robot_pos, led_color)

            # Read from front buffer (working in original commit)
            glReadBuffer(GL_FRONT)
            pixels = glReadPixels(0, 0, self.width, self.height, GL_RGB, GL_UNSIGNED_BYTE)
            image = np.frombuffer(pixels, dtype=np.uint8).reshape(self.height, self.width, 3)
            image = np.flipud(image)

            # Clear camera flash after rendering 1 frame
            if self.camera_flash:
                self.camera_flash = False

            # Cache the image for non-main thread requests
            self.cached_image = image
            self.frame_count += 1
            return image
        except Exception as e:
            logging.error(f"OpenGL rendering error: {e}")
            # Return black image on error to prevent crashes
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)
    
    def _draw_scene(self, robot_pos, led_color):
        self._draw_plate_with_cells()
        self._draw_well_labels()
        self._draw_trajectory()
        self._draw_robot(robot_pos, led_color)
        self._draw_manifold(robot_pos)
    
    def _draw_plate_with_cells(self):
        cfg = self.plate_config
        thickness = cfg['plate_thickness']
        depth = cfg['well_depth']

        min_x = 0
        min_y = 0
        max_x = self.plate_width
        max_y = self.plate_height

        for well in self.wells:
            is_current = (well == self.current_well)
            self._draw_cell_with_well(well, is_current, thickness, depth)
    
    def _draw_cell_with_well(self, well, is_current, plate_thickness, well_depth):
        cfg = self.plate_config
        cell_half_size = cfg['well_spacing'] / 2
        segments = self.WELL_SEGMENTS

        plate_thickness = plate_thickness * 0.5

        # Transform well position by plate offset
        # Well positions are plate-relative, add offset to get absolute position
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'plate'):
            plate_offset_x = self.fresco_xyz.plate['bottom_left'][0] / STEPS_PER_MM
            plate_offset_y = self.fresco_xyz.plate['bottom_left'][1] / STEPS_PER_MM
        else:
            plate_offset_x = 0
            plate_offset_y = 0

        well_abs_x = well.center_x + plate_offset_x
        well_abs_y = well.center_y + plate_offset_y

        cx = self.plate_width - well_abs_x
        cy = self.plate_height - well_abs_y
        z_plate_bottom = 0.0
        z_plate_top = plate_thickness
        z_well_rim = plate_thickness
        z_well_bottom = plate_thickness - well_depth

        if is_current:
            well_color = (0.5, 0.7, 1.0, 0.9)
            cell_color = (0.75, 0.75, 0.75, 0.95)
            outline_color = (0.0, 0.3, 1.0)
            outline_width = 3.0
        else:
            cell_color = (0.7, 0.7, 0.7, 0.95)
            outline_color = (0.3, 0.3, 0.3)
            outline_width = 1.0

            if well.pump_events:
                import time
                current_time = time.time()
                recent_events = [e for e in well.pump_events if current_time - e[0] < 10.0]
                if recent_events:
                    last_pump_idx = recent_events[-1][1]
                    pump_color = self.pump_colors[last_pump_idx % len(self.pump_colors)]
                    well_color = (*pump_color, 0.7)
                else:
                    well_color = (0.3, 0.3, 0.3, 0.9)
            else:
                well_color = (0.3, 0.3, 0.3, 0.9)

        glColor4f(*cell_color)

        x_min = cx - cell_half_size
        x_max = cx + cell_half_size
        y_min = cy - cell_half_size
        y_max = cy + cell_half_size

        corner_segments = 32
        for i in range(corner_segments):
            angle1 = 2.0 * np.pi * i / corner_segments
            angle2 = 2.0 * np.pi * (i + 1) / corner_segments

            edge_r = cell_half_size * 1.5
            x_outer1 = cx + edge_r * np.cos(angle1)
            y_outer1 = cy + edge_r * np.sin(angle1)
            x_outer2 = cx + edge_r * np.cos(angle2)
            y_outer2 = cy + edge_r * np.sin(angle2)

            x_outer1 = max(x_min, min(x_max, x_outer1))
            y_outer1 = max(y_min, min(y_max, y_outer1))
            x_outer2 = max(x_min, min(x_max, x_outer2))
            y_outer2 = max(y_min, min(y_max, y_outer2))

            x_inner1 = cx + well.radius * np.cos(angle1)
            y_inner1 = cy + well.radius * np.sin(angle1)
            x_inner2 = cx + well.radius * np.cos(angle2)
            y_inner2 = cy + well.radius * np.sin(angle2)

            glBegin(GL_QUADS)
            glVertex3f(x_inner1, y_inner1, z_plate_top)
            glVertex3f(x_inner2, y_inner2, z_plate_top)
            glVertex3f(x_outer2, y_outer2, z_plate_top)
            glVertex3f(x_outer1, y_outer1, z_plate_top)
            glEnd()

            glBegin(GL_QUADS)
            glVertex3f(x_inner1, y_inner1, z_plate_bottom)
            glVertex3f(x_inner2, y_inner2, z_plate_bottom)
            glVertex3f(x_outer2, y_outer2, z_plate_bottom)
            glVertex3f(x_outer1, y_outer1, z_plate_bottom)
            glEnd()

        for i in range(4):
            if i == 0:
                vx1, vy1, vx2, vy2 = x_min, y_min, x_max, y_min
            elif i == 1:
                vx1, vy1, vx2, vy2 = x_max, y_min, x_max, y_max
            elif i == 2:
                vx1, vy1, vx2, vy2 = x_max, y_max, x_min, y_max
            else:
                vx1, vy1, vx2, vy2 = x_min, y_max, x_min, y_min

            glBegin(GL_QUADS)
            glVertex3f(vx1, vy1, z_plate_bottom)
            glVertex3f(vx2, vy2, z_plate_bottom)
            glVertex3f(vx2, vy2, z_plate_top)
            glVertex3f(vx1, vy1, z_plate_top)
            glEnd()

        glColor4f(*well_color)

        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(cx, cy, z_well_rim)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(cx + well.radius * np.cos(angle),
                      cy + well.radius * np.sin(angle),
                      z_well_rim)
        glEnd()

        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            x = cx + well.radius * np.cos(angle)
            y = cy + well.radius * np.sin(angle)
            glVertex3f(x, y, z_well_rim)
            glVertex3f(x, y, z_well_bottom)
        glEnd()

        glColor3f(*outline_color)
        glLineWidth(outline_width)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(cx + well.radius * np.cos(angle),
                      cy + well.radius * np.sin(angle),
                      z_well_rim)
        glEnd()
    
    def _draw_well_labels(self):
        cfg = self.plate_config
        plate_thickness = cfg['plate_thickness']
        label_z = plate_thickness + 0.1

        # Get plate offset for transforming well positions
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'plate'):
            plate_offset_x = self.fresco_xyz.plate['bottom_left'][0] / STEPS_PER_MM
            plate_offset_y = self.fresco_xyz.plate['bottom_left'][1] / STEPS_PER_MM
        else:
            plate_offset_x = 0
            plate_offset_y = 0

        drawn_rows = set()
        drawn_cols = set()

        for well in self.wells:
            well_abs_x = well.center_x + plate_offset_x
            well_abs_y = well.center_y + plate_offset_y

            if well.row not in drawn_rows:
                row_label = cfg['row_labels'][well.row]
                # Row labels shift horizontally with plate, vertically with row position
                label_x = self.plate_width - plate_offset_x + self.label_offset
                label_y = self.plate_height - well_abs_y
                self._draw_text_3d(row_label, label_x, label_y, label_z, scale=self.label_scale)
                drawn_rows.add(well.row)

            if well.col not in drawn_cols:
                col_label = str(well.col + 1)
                # Column labels shift horizontally with column position, vertically with plate
                label_x = self.plate_width - well_abs_x
                label_y = self.plate_height - plate_offset_y + self.label_offset
                self._draw_text_3d(col_label, label_x, label_y, label_z, scale=self.label_scale)
                drawn_cols.add(well.col)
    
    def _draw_text_3d(self, text, x, y, z, scale=1.0):
        glPushMatrix()
        glTranslatef(x, y, z)
        glScalef(scale, scale, scale)

        glColor3f(0.2, 0.2, 0.2)
        glLineWidth(2.0)

        char_width = 0.35 if len(text) >= 2 else 0.5
        for i, char in enumerate(text):
            self._draw_character(char, i * char_width, 0)

        glPopMatrix()
    
    def _draw_character(self, char, offset_x, offset_y):
        patterns = {
            'A': [(-0.2, 0, 0, 0.4), (0, 0.4, 0.2, 0), (0.2, 0, 0, 0.4), (-0.1, 0.2, 0.1, 0.2)],
            'B': [(0, 0, 0, 0.4), (0, 0.4, 0.15, 0.4), (0.15, 0.4, 0.15, 0.2), (0.15, 0.2, 0, 0.2), 
                  (0, 0.2, 0.15, 0.2), (0.15, 0.2, 0.15, 0), (0.15, 0, 0, 0)],
            'C': [(0.2, 0, 0, 0), (0, 0, 0, 0.4), (0, 0.4, 0.2, 0.4)],
            'D': [(0, 0, 0, 0.4), (0, 0.4, 0.15, 0.3), (0.15, 0.3, 0.15, 0.1), (0.15, 0.1, 0, 0)],
            'E': [(0.2, 0, 0, 0), (0, 0, 0, 0.4), (0, 0.4, 0.2, 0.4), (0, 0.2, 0.15, 0.2)],
            'F': [(0, 0, 0, 0.4), (0, 0.4, 0.2, 0.4), (0, 0.2, 0.15, 0.2)],
            'G': [(0.2, 0.4, 0, 0.4), (0, 0.4, 0, 0), (0, 0, 0.2, 0), (0.2, 0, 0.2, 0.2), (0.2, 0.2, 0.1, 0.2)],
            'H': [(0, 0, 0, 0.4), (0.2, 0, 0.2, 0.4), (0, 0.2, 0.2, 0.2)],
            'I': [(0.05, 0, 0.05, 0.4), (0, 0, 0.1, 0), (0, 0.4, 0.1, 0.4)],
            'J': [(0.15, 0.4, 0.15, 0.1), (0.15, 0.1, 0.1, 0), (0.1, 0, 0, 0), (0, 0, 0, 0.05)],
            'K': [(0, 0, 0, 0.4), (0.2, 0.4, 0, 0.2), (0, 0.2, 0.2, 0)],
            'L': [(0, 0.4, 0, 0), (0, 0, 0.2, 0)],
            'M': [(0, 0, 0, 0.4), (0, 0.4, 0.1, 0.2), (0.1, 0.2, 0.2, 0.4), (0.2, 0.4, 0.2, 0)],
            'N': [(0, 0, 0, 0.4), (0, 0.4, 0.2, 0), (0.2, 0, 0.2, 0.4)],
            'O': [(0, 0, 0.2, 0), (0.2, 0, 0.2, 0.4), (0.2, 0.4, 0, 0.4), (0, 0.4, 0, 0)],
            'P': [(0, 0, 0, 0.4), (0, 0.4, 0.2, 0.4), (0.2, 0.4, 0.2, 0.2), (0.2, 0.2, 0, 0.2)],
            '1': [(0.1, 0, 0.1, 0.4), (0.05, 0.35, 0.1, 0.4)],
            '2': [(0, 0.4, 0.2, 0.4), (0.2, 0.4, 0.2, 0.2), (0.2, 0.2, 0, 0), (0, 0, 0.2, 0)],
            '3': [(0, 0.4, 0.2, 0.4), (0.2, 0.4, 0.2, 0), (0.2, 0, 0, 0), (0, 0.2, 0.2, 0.2)],
            '4': [(0, 0.4, 0, 0.2), (0, 0.2, 0.2, 0.2), (0.2, 0.4, 0.2, 0)],
            '5': [(0.2, 0.4, 0, 0.4), (0, 0.4, 0, 0.2), (0, 0.2, 0.2, 0.2), (0.2, 0.2, 0.2, 0), (0.2, 0, 0, 0)],
            '6': [(0.2, 0.4, 0, 0.4), (0, 0.4, 0, 0), (0, 0, 0.2, 0), (0.2, 0, 0.2, 0.2), (0.2, 0.2, 0, 0.2)],
            '7': [(0, 0.4, 0.2, 0.4), (0.2, 0.4, 0.1, 0)],
            '8': [(0, 0.2, 0.2, 0.2), (0, 0.2, 0, 0), (0, 0, 0.2, 0), (0.2, 0, 0.2, 0.2), 
                  (0.2, 0.2, 0.2, 0.4), (0.2, 0.4, 0, 0.4), (0, 0.4, 0, 0.2)],
            '9': [(0.2, 0, 0, 0), (0, 0, 0, 0.2), (0, 0.2, 0.2, 0.2), (0.2, 0.2, 0.2, 0.4), (0.2, 0.4, 0, 0.4)],
            '0': [(0, 0, 0.2, 0), (0.2, 0, 0.2, 0.4), (0.2, 0.4, 0, 0.4), (0, 0.4, 0, 0)],
        }
        
        if char in patterns:
            glBegin(GL_LINES)
            for line in patterns[char]:
                x1, y1, x2, y2 = line
                glVertex3f(offset_x + x1, offset_y + y1, 0)
                glVertex3f(offset_x + x2, offset_y + y2, 0)
            glEnd()
    
    def _get_robot_position_physical(self):
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'virtual_position'):
            pos = self.fresco_xyz.virtual_position.copy()
            return {
                'x': pos['x'] / STEPS_PER_MM,
                'y': pos['y'] / STEPS_PER_MM,
                'z': -pos['z'] / STEPS_PER_MM
            }
        return {'x': 0.0, 'y': 0.0, 'z': 0.0}

    def _get_robot_position(self):
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'virtual_position'):
            pos = self.fresco_xyz.virtual_position.copy()
            return {
                'x': self.plate_width - (pos['x'] / STEPS_PER_MM),
                'y': self.plate_height - (pos['y'] / STEPS_PER_MM),
                'z': -pos['z'] / STEPS_PER_MM
            }
        return {'x': 0.0, 'y': 0.0, 'z': 0.0}
    
    def _get_led_color(self):
        if not self.fresco_xyz:
            return (0.5, 0.5, 0.5)

        # Camera flash (yellow) - overrides everything
        if self.camera_flash:
            return (1.0, 1.0, 0.0)

        if self.collision_state:
            return (1.0, 0.0, 0.0)

        if hasattr(self.fresco_xyz, 'is_capturing') and self.fresco_xyz.is_capturing:
            return (1.0, 1.0, 0.0)

        # LED logic: white, blue, or both (blueish-white)
        white_on = hasattr(self.fresco_xyz, 'white_led_on') and self.fresco_xyz.white_led_on
        blue_on = hasattr(self.fresco_xyz, 'blue_led_on') and self.fresco_xyz.blue_led_on

        if white_on and blue_on:
            # Both white and blue: blueish-white
            return (0.7, 0.8, 1.0)
        elif blue_on:
            return (0.2, 0.4, 1.0)
        elif white_on:
            return (1.0, 1.0, 0.8)
        else:
            return (0.3, 0.3, 0.3)
    
    def _update_position_history(self, current_pos):
        if self.last_render_pos is not None:
            dx = abs(current_pos['x'] - self.last_render_pos['x'])
            dy = abs(current_pos['y'] - self.last_render_pos['y'])
            dz = abs(current_pos['z'] - self.last_render_pos['z'])
            self.is_moving = (dx > 0.01 or dy > 0.01 or dz > 0.01)

        self.last_render_pos = current_pos.copy()
    
    def _draw_trajectory(self):
        with self.position_lock:
            if len(self.position_history) < 2:
                return
            trajectory_copy = list(self.position_history)

        glColor4f(0.1, 0.3, 0.9, 0.6)
        glLineWidth(2.0)
        glBegin(GL_LINE_STRIP)
        for pos in trajectory_copy:
            glVertex3f(pos['x'], pos['y'], pos['z'])
        glEnd()
    
    def _draw_robot(self, pos, color):
        glPushMatrix()
        glTranslatef(pos['x'], pos['y'], pos['z'])

        radius = 2.0 * self.robot_scale
        height = 4.0 * self.robot_scale
        segments = 12
        
        glColor3f(*color)
        
        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)
            glVertex3f(x, y, -height/2)
            glVertex3f(x, y, height/2)
        glEnd()
        
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, height/2)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(radius * np.cos(angle), radius * np.sin(angle), height/2)
        glEnd()
        
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, -height/2)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(radius * np.cos(angle), radius * np.sin(angle), -height/2)
        glEnd()
        
        glPopMatrix()
    
    def _draw_manifold(self, robot_pos):
        if not self.fresco_xyz or not hasattr(self.fresco_xyz, 'virtual_manifold_position'):
            return

        manifold_z = robot_pos['z'] - (self.fresco_xyz.virtual_manifold_position / STEPS_PER_MM)
        tip_z = manifold_z - self.MANIFOLD_TIP_LENGTH
        
        glColor4f(0.8, 0.5, 0.2, 0.7)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(robot_pos['x'], robot_pos['y'], manifold_z)
        glVertex3f(robot_pos['x'], robot_pos['y'], tip_z)
        glEnd()
        
        glPointSize(8.0)
        glBegin(GL_POINTS)
        glVertex3f(robot_pos['x'], robot_pos['y'], tip_z)
        glEnd()
    
    def zoom_in(self):
        self.zoom_level = min(self.zoom_level * 1.2, 10.0)
    
    def zoom_out(self):
        self.zoom_level = max(self.zoom_level / 1.2, 0.1)
    
    def rotate_left(self):
        self.camera_azimuth -= 15.0
    
    def rotate_right(self):
        self.camera_azimuth += 15.0
    
    def rotate_up(self):
        self.camera_elevation = min(self.camera_elevation + 10.0, 89.0)
    
    def rotate_down(self):
        self.camera_elevation = max(self.camera_elevation - 10.0, -89.0)
    
    def center_on_robot(self):
        self.target_position = self._get_robot_position()
    
    def reset_view(self):
        self.camera_distance = 250.0
        self.camera_elevation = 30.0
        self.camera_azimuth = 45.0
        self.zoom_level = 1.0
        self.target_position = {'x': self.plate_width / 2, 'y': self.plate_height / 2, 'z': 0.0}

    def pan_left(self):
        self.target_position['y'] -= 5.0

    def pan_right(self):
        self.target_position['y'] += 5.0

    def pan_up(self):
        self.target_position['x'] -= 5.0

    def pan_down(self):
        self.target_position['x'] += 5.0

    def should_update_frequently(self):
        return self.is_moving or self.camera_flash

    def set_exposure(self, millis: int):
        pass
    
    def set_auto_exposure(self, auto: bool):
        pass
    
    def __del__(self):
        pygame.quit()
