import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional


class FrescoRenderer:
    """OpenGL-based 3D renderer for Fresco microscope emulator."""
    
    # 96-well plate dimensions (SBS standard) in mm
    PLATE_ROWS = 8
    PLATE_COLS = 12
    WELL_DIAMETER = 6.5
    WELL_SPACING = 9.0
    WELL_DEPTH = 10.5
    PLATE_WIDTH = (PLATE_COLS - 1) * WELL_SPACING
    PLATE_HEIGHT = (PLATE_ROWS - 1) * WELL_SPACING
    PLATE_THICKNESS = 2.0
    
    # Hardware constraints
    MANIFOLD_TIP_LENGTH = 20.0
    SAFE_CLEARANCE_Z = 5.0
    
    # Unit conversion: stepper motor steps to mm
    STEPS_PER_MM = 200.0
    
    # Rendering parameters
    WELL_CIRCLE_SEGMENTS = 12
    TRAJECTORY_MAX_POINTS = 100
    
    def __init__(self, image_processor, fresco_xyz):
        self.image_processor = image_processor
        self.fresco_xyz = fresco_xyz
        
        self.width = 800
        self.height = 800
        
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height), OPENGL | HIDDEN)
        pygame.display.set_caption("Fresco 3D View")
        
        self._init_opengl()
        
        # Camera state
        self.camera_distance = 250.0
        self.camera_elevation = 30.0
        self.camera_azimuth = 45.0
        self.zoom_level = 1.0
        self.target_position = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        
        # Robot state
        self.position_history: List[Dict[str, float]] = []
        self.collision_warnings: List[Dict] = []
        
        # Display lists for pre-compiled geometry
        self.well_plate_display_list = None
        self._compile_geometry()
        
        # Movement tracking
        self.frame_count = 0
        self.last_render_pos = None
        self.is_moving = False
        self.show_grid = False
        
        logging.info("OpenGL Renderer initialized")
    
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
    
    def _compile_geometry(self):
        self.well_plate_display_list = glGenLists(1)
        glNewList(self.well_plate_display_list, GL_COMPILE)
        self._draw_well_plate_geometry()
        glEndList()
        logging.info("Geometry compiled into display lists")
    
    def _draw_well_plate_geometry(self):
        half_width = self.PLATE_WIDTH / 2
        half_height = self.PLATE_HEIGHT / 2
        
        # Draw plate base BELOW the wells (at Z = -PLATE_THICKNESS)
        # This way wells are holes going down into the plate
        glColor4f(0.85, 0.85, 0.85, 0.95)
        glBegin(GL_QUADS)
        glVertex3f(-half_width - 10, -half_height - 10, -self.PLATE_THICKNESS)
        glVertex3f(half_width + 10, -half_height - 10, -self.PLATE_THICKNESS)
        glVertex3f(half_width + 10, half_height + 10, -self.PLATE_THICKNESS)
        glVertex3f(-half_width - 10, half_height + 10, -self.PLATE_THICKNESS)
        glEnd()
        
        # Plate sides (thickness)
        glColor4f(0.8, 0.8, 0.8, 0.9)
        
        # Front edge
        glBegin(GL_QUADS)
        glVertex3f(-half_width - 10, -half_height - 10, 0)
        glVertex3f(half_width + 10, -half_height - 10, 0)
        glVertex3f(half_width + 10, -half_height - 10, -self.PLATE_THICKNESS)
        glVertex3f(-half_width - 10, -half_height - 10, -self.PLATE_THICKNESS)
        glEnd()
        
        # Back edge
        glBegin(GL_QUADS)
        glVertex3f(-half_width - 10, half_height + 10, 0)
        glVertex3f(half_width + 10, half_height + 10, 0)
        glVertex3f(half_width + 10, half_height + 10, -self.PLATE_THICKNESS)
        glVertex3f(-half_width - 10, half_height + 10, -self.PLATE_THICKNESS)
        glEnd()
        
        # Left edge
        glBegin(GL_QUADS)
        glVertex3f(-half_width - 10, -half_height - 10, 0)
        glVertex3f(-half_width - 10, half_height + 10, 0)
        glVertex3f(-half_width - 10, half_height + 10, -self.PLATE_THICKNESS)
        glVertex3f(-half_width - 10, -half_height - 10, -self.PLATE_THICKNESS)
        glEnd()
        
        # Right edge
        glBegin(GL_QUADS)
        glVertex3f(half_width + 10, -half_height - 10, 0)
        glVertex3f(half_width + 10, half_height + 10, 0)
        glVertex3f(half_width + 10, half_height + 10, -self.PLATE_THICKNESS)
        glVertex3f(half_width + 10, -half_height - 10, -self.PLATE_THICKNESS)
        glEnd()
        
        # Top outline
        glColor3f(0.2, 0.2, 0.2)
        glLineWidth(2.0)
        glBegin(GL_LINE_LOOP)
        glVertex3f(-half_width - 10, -half_height - 10, 0)
        glVertex3f(half_width + 10, -half_height - 10, 0)
        glVertex3f(half_width + 10, half_height + 10, 0)
        glVertex3f(-half_width - 10, half_height + 10, 0)
        glEnd()
        
        # Draw all 96 wells as depressions going down from Z=0
        well_radius = self.WELL_DIAMETER / 2
        for row in range(self.PLATE_ROWS):
            for col in range(self.PLATE_COLS):
                well_x = -half_width + col * self.WELL_SPACING
                well_y = -half_height + row * self.WELL_SPACING
                self._draw_well(well_x, well_y, 0, well_radius, self.WELL_DEPTH)
    
    def _draw_well(self, x: float, y: float, z_top: float, radius: float, depth: float):
        """Draw a well as a cylindrical depression in the plate."""
        z_bottom = z_top - depth
        segments = self.WELL_CIRCLE_SEGMENTS
        
        # Well interior (darker to show it's a hole)
        glColor4f(0.3, 0.3, 0.3, 0.9)
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(x, y, z_bottom)  # Center of bottom
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(x + radius * np.cos(angle), 
                      y + radius * np.sin(angle), 
                      z_bottom)
        glEnd()
        
        # Well walls (cylinder sides)
        glColor4f(0.4, 0.4, 0.4, 0.8)
        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            cx = x + radius * np.cos(angle)
            cy = y + radius * np.sin(angle)
            glVertex3f(cx, cy, z_top)
            glVertex3f(cx, cy, z_bottom)
        glEnd()
        
        # Top rim (dark edge)
        glColor3f(0.2, 0.2, 0.2)
        glLineWidth(1.5)
        glBegin(GL_LINE_LOOP)
        for i in range(segments):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(x + radius * np.cos(angle), 
                      y + radius * np.sin(angle), 
                      z_top)
        glEnd()
    
    def get_current_image(self) -> np.ndarray:
        """Render current frame and return as numpy array (RGB, 800x800x3)."""
        current_pos = self._get_robot_position()
        led_color = self._get_led_color()
        
        self._update_position_history(current_pos)
        self._check_collisions(current_pos)
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        # Camera positioning
        camera_x = self.target_position['x'] + self.camera_distance * np.cos(np.radians(self.camera_elevation)) * np.sin(np.radians(self.camera_azimuth))
        camera_y = self.target_position['y'] + self.camera_distance * np.cos(np.radians(self.camera_elevation)) * np.cos(np.radians(self.camera_azimuth))
        camera_z = self.target_position['z'] + self.camera_distance * np.sin(np.radians(self.camera_elevation))
        
        gluLookAt(
            camera_x / self.zoom_level, camera_y / self.zoom_level, camera_z / self.zoom_level,
            self.target_position['x'], self.target_position['y'], self.target_position['z'],
            0, 0, 1
        )
        
        # Draw scene
        glCallList(self.well_plate_display_list)
        self._draw_trajectory()
        self._draw_robot(current_pos, led_color)
        self._draw_manifold()
        
        # Read framebuffer
        glReadBuffer(GL_FRONT)
        pixels = glReadPixels(0, 0, self.width, self.height, GL_RGB, GL_UNSIGNED_BYTE)
        image = np.frombuffer(pixels, dtype=np.uint8).reshape(self.height, self.width, 3)
        image = np.flipud(image)
        
        self.frame_count += 1
        return image
    
    def _get_robot_position(self) -> Dict[str, float]:
        """Get current robot position converted from steps to mm."""
        if self.fresco_xyz and hasattr(self.fresco_xyz, 'virtual_position'):
            pos = self.fresco_xyz.virtual_position.copy()
            return {
                'x': pos['x'] / self.STEPS_PER_MM,
                'y': pos['y'] / self.STEPS_PER_MM,
                'z': pos['z'] / self.STEPS_PER_MM
            }
        return {'x': 0.0, 'y': 0.0, 'z': 0.0}
    
    def _get_led_color(self) -> Tuple[float, float, float]:
        if not self.fresco_xyz:
            return (0.5, 0.5, 0.5)
        
        if hasattr(self.fresco_xyz, 'blue_led_on') and self.fresco_xyz.blue_led_on:
            return (0.2, 0.4, 1.0)
        elif hasattr(self.fresco_xyz, 'white_led_on') and self.fresco_xyz.white_led_on:
            return (1.0, 1.0, 0.8)
        else:
            return (0.3, 0.3, 0.3)
    
    def _update_position_history(self, current_pos: Dict[str, float]):
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
    
    def _draw_robot(self, pos: Dict[str, float], color: Tuple[float, float, float]):
        """Draw robot as a small vertical cylinder."""
        glPushMatrix()
        glTranslatef(pos['x'], pos['y'], pos['z'])
        
        radius = 2.0
        height = 4.0
        segments = 12
        
        glColor3f(*color)
        
        # Cylinder body
        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)
            glVertex3f(x, y, -height/2)
            glVertex3f(x, y, height/2)
        glEnd()
        
        # Top cap
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, height/2)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(radius * np.cos(angle), radius * np.sin(angle), height/2)
        glEnd()
        
        # Bottom cap
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, -height/2)
        for i in range(segments + 1):
            angle = 2.0 * np.pi * i / segments
            glVertex3f(radius * np.cos(angle), radius * np.sin(angle), -height/2)
        glEnd()
        
        glPopMatrix()
    
    def _draw_manifold(self):
        """Draw manifold as a vertical line from manifold height to tip."""
        if not self.fresco_xyz or not hasattr(self.fresco_xyz, 'virtual_manifold_position'):
            return
        
        manifold_z = self.fresco_xyz.virtual_manifold_position / self.STEPS_PER_MM
        robot_pos = self._get_robot_position()
        tip_z = manifold_z - self.MANIFOLD_TIP_LENGTH
        
        glColor4f(0.8, 0.5, 0.2, 0.7)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glVertex3f(robot_pos['x'], robot_pos['y'], manifold_z)
        glVertex3f(robot_pos['x'], robot_pos['y'], tip_z)
        glEnd()
        
        # Tip point
        glPointSize(8.0)
        glBegin(GL_POINTS)
        glVertex3f(robot_pos['x'], robot_pos['y'], tip_z)
        glEnd()
    
    def _check_collisions(self, pos: Dict[str, float]):
        """Check for collision conditions."""
        self.collision_warnings = []
        
        if not self.fresco_xyz or not hasattr(self.fresco_xyz, 'virtual_manifold_position'):
            return
        
        manifold_z = self.fresco_xyz.virtual_manifold_position / self.STEPS_PER_MM
        tip_z = manifold_z - self.MANIFOLD_TIP_LENGTH
        
        over_well, well_info = self._is_over_well(pos['x'], pos['y'])
        
        # Collision: tip below well bottom
        if tip_z < -self.WELL_DEPTH and not over_well:
            self.collision_warnings.append({
                'type': 'CRITICAL',
                'message': f'COLLISION: Manifold tip at {tip_z:.1f}mm, through plate!',
                'position': pos.copy()
            })
        elif tip_z < self.SAFE_CLEARANCE_Z and not over_well:
            self.collision_warnings.append({
                'type': 'WARNING',
                'message': f'Low clearance: tip at {tip_z:.1f}mm',
                'position': pos.copy()
            })
    
    def _is_over_well(self, x: float, y: float) -> Tuple[bool, Optional[Dict]]:
        """Check if position (x, y) is over a well."""
        half_width = self.PLATE_WIDTH / 2
        half_height = self.PLATE_HEIGHT / 2
        well_radius = self.WELL_DIAMETER / 2
        
        for row in range(self.PLATE_ROWS):
            for col in range(self.PLATE_COLS):
                well_x = -half_width + col * self.WELL_SPACING
                well_y = -half_height + row * self.WELL_SPACING
                
                distance = np.sqrt((x - well_x)**2 + (y - well_y)**2)
                
                if distance <= well_radius:
                    return True, {
                        'row': row,
                        'col': col,
                        'label': f"{chr(65 + row)}{col + 1}",
                        'x': well_x,
                        'y': well_y
                    }
        
        return False, None
    
    # Camera controls
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
    
    def should_update_frequently(self) -> bool:
        return self.is_moving
    
    # Stub methods for camera interface compatibility
    def set_exposure(self, millis: int):
        pass
    
    def set_auto_exposure(self, auto: bool):
        pass
    
    def __del__(self):
        if self.well_plate_display_list:
            glDeleteLists(self.well_plate_display_list, 1)
        pygame.quit()
