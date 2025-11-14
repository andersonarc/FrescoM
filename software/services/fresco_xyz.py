from plates import get_plate_config
from services.services import global_services
import logging


class CollisionWarning(Warning):
    """Warning raised for potential collision issues."""
    pass


class FrescoXYZ:
    STEPS_PER_MM = 200.0
    SAFE_DEFAULT_Z = -4000  # -20mm above plate (negative is up)

    def __init__(self, virtual_only: bool, plate_type):
        if not virtual_only:
            self.serial_service = global_services.serial_service
            print('Serial service initialized')
        else:
            print('Running in virtual-only mode')

        self.plate = get_plate_config(plate_type)
        self.virtual_only = virtual_only
        self.virtual_position = {'x': self.plate['bottom_left'][0], 'y': self.plate['bottom_left'][1], 'z': self.SAFE_DEFAULT_Z}
        self.virtual_pump_positions = {}
        self.virtual_manifold_position = 0
        self.white_led_on = False
        self.blue_led_on = False
        self.is_capturing = False
        self.topLeftPosition = (-1, -1)
        self.bottomRightPosition = (-1, -1)
        
        self.renderer = None
        self.stop_requested = False
        self.collision_warnings_enabled = True

    def send(self, message: str):
        logging.debug(f"[FrescoXYZ] Sending: {message}")
        self._emulate_command(message)
        if not self.virtual_only:
            self.serial_service.current_connection.send_message_line(message)

    def execute_command(self, message: str) -> str:
        logging.debug(f"[FrescoXYZ] Executing: {message}")
        response = self._emulate_command(message)
        if not self.virtual_only:
            return self.serial_service.current_connection.execute_command_sync(message)
        return response
        
    def _emulate_command(self, message: str) -> str:
        parts = message.strip().split()

        if not parts:
            logging.warning(f"[Emulator] Malformed message: {message}")
            return "OK"

        cmd = parts[0]

        if cmd == "Delta" and len(parts) >= 4:
            try:
                dx, dy, dz = float(parts[1]), float(parts[2]), float(parts[3])
                self.virtual_position['x'] += dx
                self.virtual_position['y'] += dy
                self.virtual_position['z'] += dz

                if self.renderer:
                    x_mm = self.virtual_position['x'] / self.STEPS_PER_MM
                    y_mm = self.virtual_position['y'] / self.STEPS_PER_MM
                    z_mm = -self.virtual_position['z'] / self.STEPS_PER_MM
                    self.renderer.record_position(x_mm, y_mm, z_mm)

                logging.info(f"[Emulator] Delta ({dx}, {dy}, {dz}) -> {self.virtual_position}")
            except ValueError:
                pass

        elif cmd == "DeltaPump" and len(parts) >= 3:
            try:
                pump_idx = int(parts[1])
                delta = float(parts[2])
                if pump_idx not in self.virtual_pump_positions:
                    self.virtual_pump_positions[pump_idx] = 0
                self.virtual_pump_positions[pump_idx] += delta
                
                # Record pump event in renderer
                if self.renderer:
                    self.renderer.record_pump_event(pump_idx, delta)
                
                logging.info(f"[Emulator] Pump {pump_idx} -> {self.virtual_pump_positions[pump_idx]}")
            except ValueError:
                pass

        elif cmd == "ManifoldDelta" and len(parts) >= 2:
            try:
                delta = float(parts[1])
                self.virtual_manifold_position += delta
                logging.info(f"[Emulator] Manifold -> {self.virtual_manifold_position}")
            except ValueError:
                pass

        elif cmd == "SetPosition" and len(parts) >= 4:
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                self.virtual_position = {'x': x, 'y': y, 'z': z}

                if self.renderer:
                    x_mm = self.virtual_position['x'] / self.STEPS_PER_MM
                    y_mm = self.virtual_position['y'] / self.STEPS_PER_MM
                    z_mm = -self.virtual_position['z'] / self.STEPS_PER_MM
                    self.renderer.record_position(x_mm, y_mm, z_mm)

                logging.info(f"[Emulator] SetPosition -> {self.virtual_position}")
            except ValueError:
                pass

        elif cmd == "Zero":
            self.virtual_position = {'x': self.plate['bottom_left'][0], 'y': self.plate['bottom_left'][1], 'z': self.SAFE_DEFAULT_Z}

            if self.renderer:
                x_mm = self.virtual_position['x'] / self.STEPS_PER_MM
                y_mm = self.virtual_position['y'] / self.STEPS_PER_MM
                z_mm = -self.virtual_position['z'] / self.STEPS_PER_MM
                self.renderer.record_position(x_mm, y_mm, z_mm)

            logging.info("[Emulator] Zero XYZ (raised to safe height)")

        elif cmd == "ManifoldZero":
            self.virtual_manifold_position = 0
            logging.info("[Emulator] Zero Manifold")

        elif cmd == "VerticalZero":
            self.virtual_position['z'] = self.SAFE_DEFAULT_Z

            if self.renderer:
                x_mm = self.virtual_position['x'] / self.STEPS_PER_MM
                y_mm = self.virtual_position['y'] / self.STEPS_PER_MM
                z_mm = -self.virtual_position['z'] / self.STEPS_PER_MM
                self.renderer.record_position(x_mm, y_mm, z_mm)

            logging.info("[Emulator] Zero Z (raised to safe height)")

        elif cmd == "GetTopLeftBottomRightCoordinates":
            logging.info(f"[Emulator] TopLeft: {self.topLeftPosition}, BottomRight: {self.bottomRightPosition}")
            return f"OK {self.topLeftPosition[0]} {self.topLeftPosition[1]} {self.bottomRightPosition[0]} {self.bottomRightPosition[1]}"

        elif cmd == "RememberTopLeft":
            curr_x = int(self.virtual_position['x'])
            curr_y = int(self.virtual_position['y'])
            self.topLeftPosition = (curr_x, curr_y)

            # Top-left well should be at bottom_left.x, top_right.y
            old_bottom_left = self.plate['bottom_left']
            old_top_right = self.plate['top_right']
            self.plate['bottom_left'] = (curr_x, old_bottom_left[1])
            self.plate['top_right'] = (old_top_right[0], curr_y)

            logging.info(f"[Emulator] Remembered top-left position: ({curr_x}, {curr_y})")
            logging.info(f"[Emulator] Plate bounds: bottom_left={self.plate['bottom_left']}, top_right={self.plate['top_right']}")

        elif cmd == "RememberBottomRight":
            curr_x = int(self.virtual_position['x'])
            curr_y = int(self.virtual_position['y'])
            self.bottomRightPosition = (curr_x, curr_y)

            # Bottom-right well should be at top_right.x, bottom_left.y
            old_bottom_left = self.plate['bottom_left']
            old_top_right = self.plate['top_right']
            self.plate['bottom_left'] = (old_bottom_left[0], curr_y)
            self.plate['top_right'] = (curr_x, old_top_right[1])

            logging.info(f"[Emulator] Remembered bottom-right position: ({curr_x}, {curr_y})")
            logging.info(f"[Emulator] Plate bounds: bottom_left={self.plate['bottom_left']}, top_right={self.plate['top_right']}")

        elif cmd == "SwitchLedW" and len(parts) >= 2:
            self.white_led_on = parts[1] == "1"
            logging.info(f"[Emulator] White LED: {'ON' if self.white_led_on else 'OFF'}")
        
        elif cmd == "SwitchLedB" and len(parts) >= 2:
            self.blue_led_on = parts[1] == "1"
            logging.info(f"[Emulator] Blue LED: {'ON' if self.blue_led_on else 'OFF'}")

        return "OK"
    
    def _check_collision(self, new_pos_steps):
        """Advisory collision check - warns but doesn't block."""
        if not self.renderer or not self.collision_warnings_enabled:
            return None
        
        x_mm = new_pos_steps['x'] / self.STEPS_PER_MM
        y_mm = new_pos_steps['y'] / self.STEPS_PER_MM
        z_mm = -new_pos_steps['z'] / self.STEPS_PER_MM

        margin = 15
        min_x = -margin
        min_y = -margin
        max_x = self.renderer.plate_width + margin
        max_y = self.renderer.plate_height + margin

        warnings = []

        if x_mm < min_x or x_mm > max_x:
            warnings.append(f"X out of bounds: {x_mm:.1f}mm (range {min_x:.1f} to {max_x:.1f}mm)")
        if y_mm < min_y or y_mm > max_y:
            warnings.append(f"Y out of bounds: {y_mm:.1f}mm (range {min_y:.1f} to {max_y:.1f}mm)")
        
        well = self.renderer.get_well_at_position(x_mm, y_mm)
        manifold_z_mm = z_mm - (self.virtual_manifold_position / self.STEPS_PER_MM)
        tip_z = manifold_z_mm - 20.0

        plate_top = self.renderer.plate_config['plate_thickness']

        if well is None and tip_z > -2.0 and tip_z < plate_top + 2.0:
            warnings.append(f"Manifold tip near plate surface at Z={tip_z:.1f}mm")
        elif well and tip_z < (plate_top - well.depth - 0.5):
            warnings.append(f"Manifold tip penetrating well {well.label} bottom")
        
        self.renderer.collision_state = bool(warnings)
        
        return warnings if warnings else None
    
    def request_stop(self):
        """Request protocol stop - should be checked in protocol loops."""
        self.stop_requested = True
        logging.warning("Protocol stop requested")
    
    def should_stop(self) -> bool:
        """Check if protocol should stop."""
        return self.stop_requested
    
    def reset_stop_flag(self):
        """Reset stop flag for new protocol."""
        self.stop_requested = False

    def white_led_switch(self, state: bool):
        message = 'SwitchLedW 1' if state else 'SwitchLedW 0'
        self.send(message)

    def blue_led_switch(self, state: bool):
        message = 'SwitchLedB 1' if state else 'SwitchLedB 0'
        self.send(message)

    def delta(self, x: float, y: float, z: float):
        new_pos = {
            'x': self.virtual_position['x'] + x,
            'y': self.virtual_position['y'] + y,
            'z': self.virtual_position['z'] + z
        }
        
        warnings = self._check_collision(new_pos)
        if warnings:
            for warning in warnings:
                logging.warning(f"COLLISION WARNING: {warning}")
                import warnings as warn_module
                warn_module.warn(warning, CollisionWarning, stacklevel=2)
        
        message = f'Delta {x} {y} {z}'
        self.execute_command(message)

    def delta_pump(self, pump_index: int, delta: float):
        message = f'DeltaPump {pump_index} {delta}'
        self.execute_command(message)

    def manifold_delta(self, delta: float):
        message = f'ManifoldDelta {delta}'
        self.execute_command(message)

    def set_position(self, x: float, y: float, z: float):
        new_pos = {'x': x, 'y': y, 'z': z}
        
        warnings = self._check_collision(new_pos)
        if warnings:
            for warning in warnings:
                logging.warning(f"COLLISION WARNING: {warning}")
                import warnings as warn_module
                warn_module.warn(warning, CollisionWarning, stacklevel=2)
        
        message = f'SetPosition {x} {y} {z}'
        self.execute_command(message)

    def go_to_zero(self):
        self.execute_command('Zero')

    def go_to_zero_manifold(self):
        self.execute_command('ManifoldZero')

    def go_to_zero_z(self):
        self.execute_command('VerticalZero')

    def remember_top_left_position(self):
        self.go_to_zero_z()
        self.execute_command('RememberTopLeft')

    def remember_bottom_right_position(self):
        self.go_to_zero_z()
        self.execute_command('RememberBottomRight')

    def update_top_left_bottom_right(self):
        coordinates_response = self.execute_command('GetTopLeftBottomRightCoordinates')
        tokens = coordinates_response.split(' ')
        self.topLeftPosition = (int(tokens[1]), int(tokens[2]))
        self.bottomRightPosition = (int(tokens[3]), int(tokens[4]))
        print(f"TopLeft: {self.topLeftPosition}, BottomRight: {self.bottomRightPosition}")

    def get_step_for_1_well(self, number_of_wells_x: int, number_of_wells_y: int):
        return (abs(self.topLeftPosition[0] - self.bottomRightPosition[0]) // (number_of_wells_x - 1),
                abs(self.topLeftPosition[1] - self.bottomRightPosition[1]) // (number_of_wells_y - 1))
