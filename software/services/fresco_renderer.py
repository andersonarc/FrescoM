import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np
import logging
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
    TRAJECTORY_MAX_POINTS = 100
    
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
        self.label_font = pygame.font.SysFont('Arial', 24, bold=True)
        
        self._init_opengl()
        
        self.camera_distance = 250.0
        self.camera_elevation = 30.0
        self.camera_azimuth = 45.0
        self.zoom_level = 1.0
        self.target_position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        
        self.wells = self._create_wells()
        self.current_well = None
        
        self.position_history = []
        self.frame_count = 0
        self.last_render_pos = None
        self.is_moving = False
        self.collision_state = False
        
        self.pump_colors = [
            (1.0, 0.3, 0.3), (0.3, 1.0, 0.3), (0.3, 0.3, 1.0), (1.0, 1.0, 0.3),
            (1.0, 0.3, 1.0), (0.3, 1.0, 1.0), (1.0, 0.6, 0.3), (0.6, 0.3, 1.0),
        ]
        
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
        
        half_width = self.plate_width / 2
        half_height = self.plate_height / 2
        well_radius = cfg['well_diameter'] / 2
        
        for row in range(cfg['rows']):
            for col in range(cfg['cols']):
                x = -half_width + col * cfg['well_spacing']
                y = -half_height + row * cfg['well_spacing']
                label = f"{cfg['row_labels'][row]}{col + 1}"
                well = Well(row, col, x, y, well_radius, cfg['well_depth'], label)
                wells.append(well)
        
        return wells
    
    def get_well_at_position(self, x_mm, y_mm):
        for well in self.wells:
            if well.contains_point(x_mm, y_mm):
                return well
        return None
    
    def record_pump_event(self, pump_index, volume):
        if self.current_well:
            self.current_well.add_pump_event(pump_index, volume)
            logging.info(f"Pump event recorded: Well {self.current_well.label}, Pump {pump_index}, Volume {volume}")
    
    def get_current_image(self):
        robot_pos = self._get_robot_position()
        self.current_well = self.get_well_at_position(robot_pos['x'], robot_pos['y'])
        
        led_color = self._get_led_color()
        self._update_position_history(robot_pos)
        
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
        
        glReadBuffer(GL_FRONT)
        pixels = glReadPixels(0, 0, self.width, self.height, GL_RGB, GL_UNSIGNED_BYTE)
        image = np.frombuffer(pixels, dtype=np.uint8).reshape(self.height, self.width, 3)
        image = np.flipud(image)
        
        self.frame_count += 1
        return image
    
    def _draw_scene(self, robot_pos, led_color):
        self._draw_plate_with_cells()
        self._draw_well_labels()
        self._draw_trajectory()
        self._draw_robot(robot_pos, led_color)
        self._draw_manifold(robot_pos)
    
    def _draw_plate_with_cells(self):
        cfg = self.plate_config
        half_width = self.plate_width / 2
        half_height = self.plate_height / 2
        margin = 10.0
        thickness = cfg['plate_thickness']
        depth = cfg['well_depth']
        
        # Plate edges only
        glColor4f(0.8, 0.8, 0.8, 0.9)
        edges = [
            [(-half_width - margin, -half_height - margin), (half_width + margin, -half_height - margin)],
            [(-half_width - margin, half_height + margin), (half_width + margin, half_height + margin)],
            [(-half_width - margin, -half_height - margin), (-half_width - margin, half_height + margin)],
            [(half_width + margin, -half_height - margin), (half_width + margin, half_height + margin)]
        ]
        
        for (x1, y1), (x2, y2) in edges:
            glBegin(GL_QUADS)
            glVertex3f(x1, y1, 0)
            glVertex3f(x2, y2, 0)
            glVertex3f(x2, y2, thickness)
            glVertex3f(x1, y1, thickness)
            glEnd()
        
        # Draw cells with indented wells
        for well in self.wells:
            is_current = (well == self.current_well)
            self._draw_cell_with_well(well, is_current, thickness, depth)
        
        # Plate border
        glColor3f(0.2, 0.2, 0.2)
        glLineWidth(2.0)
        glBegin(GL_LINE_LOOP)
        glVertex3f(-half_width - margin, -half_height - margin, thickness)
        glVertex3f(half_width + margin, -half_height - margin, thickness)
        glVertex3f(half_width + margin, half_height + margin, thickness)
        glVertex3f(-half_width - margin, half_height + margin, thickness)
        glEnd()
    
    def _draw_cell_with_well(self, well, is_current, plate_thickness, well_depth):
        cfg = self.plate_config
        cell_size = cfg['well_spacing'] * 0.45
        segments = self.WELL_SEGMENTS
        
        cx, cy = well.center_x, well.center_y
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
        
        for i in range(segments):
            angle1 = 2.0 * np.pi * i / segments
            angle2 = 2.0 * np.pi * (i + 1) / segments
            
            x_inner1 = cx + well.radius * np.cos(angle1)
            y_inner1 = cy + well.radius * np.sin(angle1)
            x_inner2 = cx + well.radius * np.cos(angle2)
            y_inner2 = cy + well.radius * np.sin(angle2)
            
            x_outer1 = cx + (cell_size * 1.5) * np.cos(angle1)
            y_outer1 = cy + (cell_size * 1.5) * np.sin(angle1)
            x_outer2 = cx + (cell_size * 1.5) * np.cos(angle2)
            y_outer2 = cy + (cell_size * 1.5) * np.sin(angle2)
            
            x_outer1 = np.clip(x_outer1, cx - cell_size, cx + cell_size)
            y_outer1 = np.clip(y_outer1, cy - cell_size, cy + cell_size)
            x_outer2 = np.clip(x_outer2, cx - cell_size, cx + cell_size)
            y_outer2 = np.clip(y_outer2, cy - cell_size, cy + cell_size)
            
            glBegin(GL_QUADS)
            glVertex3f(x_outer1, y_outer1, z_plate_top)
            glVertex3f(x_outer2, y_outer2, z_plate_top)
            glVertex3f(x_inner2, y_inner2, z_well_rim)
            glVertex3f(x_inner1, y_inner1, z_well_rim)
            glEnd()
        
        corners = [
            (cx - cell_size, cy - cell_size),
            (cx + cell_size, cy - cell_size),
            (cx + cell_size, cy + cell_size),
            (cx - cell_size, cy + cell_size)
        ]
        for i in range(4):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % 4]
            glBegin(GL_QUADS)
            glVertex3f(x1, y1, z_plate_bottom)
            glVertex3f(x2, y2, z_plate_bottom)
            glVertex3f(x2, y2, z_plate_top)
            glVertex3f(x1, y1, z_plate_top)
            glEnd()
        
        glColor4f(*well_color)
        
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(cx, cy, z_well_bottom)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(cx + well.radius * np.cos(angle),
                      cy + well.radius * np.sin(angle),
                      z_well_bottom)
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
        pass
    
    def _draw_text_3d(self, text, x, y, z, scale=1.0):
        glPushMatrix()
        glTranslatef(x, y, z)
        glScalef(scale, scale, scale)
        
        glColor3f(0.2, 0.2, 0.2)
        glLineWidth(2.0)
        
        char_width = 0.5
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
    
    def _get_robot_position(self):
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'virtual_position'):
            pos = self.fresco_xyz.virtual_position.copy()
            return {
                'x': pos['x'] / STEPS_PER_MM,
                'y': pos['y'] / STEPS_PER_MM,
                'z': -pos['z'] / STEPS_PER_MM
            }
        return {'x': 0.0, 'y': 0.0, 'z': 0.0}
    
    def _get_led_color(self):
        if not self.fresco_xyz:
            return (0.5, 0.5, 0.5)
        
        if self.collision_state:
            return (1.0, 0.0, 0.0)
        
        if hasattr(self.fresco_xyz, 'is_capturing') and self.fresco_xyz.is_capturing:
            return (1.0, 1.0, 0.0)
        
        if hasattr(self.fresco_xyz, 'blue_led_on') and self.fresco_xyz.blue_led_on:
            return (0.2, 0.4, 1.0)
        elif hasattr(self.fresco_xyz, 'white_led_on') and self.fresco_xyz.white_led_on:
            return (1.0, 1.0, 0.8)
        else:
            return (0.3, 0.3, 0.3)
    
    def _update_position_history(self, current_pos):
        self.position_history.append(current_pos.copy())
        if len(self.position_history) > self.TRAJECTORY_MAX_POINTS:
            self.position_history.pop(0)
        
        if self.last_render_pos is not None:
            dx = abs(current_pos['x'] - self.last_render_pos['x'])
            dy = abs(current_pos['y'] - self.last_render_pos['y'])
            dz = abs(current_pos['z'] - self.last_render_pos['z'])
            self.is_moving = (dx > 0.1 or dy > 0.1 or dz > 0.1)
        
        self.last_render_pos = current_pos.copy()
    
    def _draw_trajectory(self):
        if len(self.position_history) < 2:
            return
        
        glColor4f(0.1, 0.3, 0.9, 0.6)
        glLineWidth(2.0)
        glBegin(GL_LINE_STRIP)
        for pos in self.position_history:
            glVertex3f(pos['x'], pos['y'], pos['z'])
        glEnd()
    
    def _draw_robot(self, pos, color):
        glPushMatrix()
        glTranslatef(pos['x'], pos['y'], pos['z'])
        
        radius = 2.0
        height = 4.0
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
        
        manifold_z = -self.fresco_xyz.virtual_manifold_position / STEPS_PER_MM
        tip_z = manifold_z + self.MANIFOLD_TIP_LENGTH
        
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
        self.target_position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
    
    def should_update_frequently(self):
        return self.is_moving
    
    def set_exposure(self, millis: int):
        pass
    
    def set_auto_exposure(self, auto: bool):
        pass
    
    def __del__(self):
        pygame.quit()
