from services.services import global_services
import logging


class FrescoXYZ:

    def __init__(self, virtual_only: bool):
        if not virtual_only:
            self.serial_service = global_services.serial_service
            print('Serial service initialized')
        else:
            print('Running in virtual-only mode')

        self.virtual_only = virtual_only
        self.virtual_position = {'x': 0, 'y': 0, 'z': 0}
        self.virtual_pump_positions = {}
        self.virtual_manifold_position = 0
        self.white_led_on = False
        self.blue_led_on = False
        self.topLeftPosition = (-1, -1)
        self.bottomRightPosition = (-1, -1)

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
        """Emulate hardware commands in virtual mode."""
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
                logging.info(f"[Emulator] SetPosition -> {self.virtual_position}")
            except ValueError:
                pass

        elif cmd == "Zero":
            self.virtual_position = {'x': 0, 'y': 0, 'z': 0}
            logging.info("[Emulator] Zero XYZ")

        elif cmd == "ManifoldZero":
            self.virtual_manifold_position = 0
            logging.info("[Emulator] Zero Manifold")

        elif cmd == "VerticalZero":
            self.virtual_position['z'] = 0
            logging.info("[Emulator] Zero Z")

        elif cmd == "GetTopLeftBottomRightCoordinates":
            logging.info(f"[Emulator] TopLeft: {self.topLeftPosition}, BottomRight: {self.bottomRightPosition}")
            return f"OK {self.topLeftPosition[0]} {self.topLeftPosition[1]} {self.bottomRightPosition[0]} {self.bottomRightPosition[1]}"

        elif cmd == "RememberTopLeft":
            self.topLeftPosition = (int(self.virtual_position['x']), int(self.virtual_position['y']))
            logging.info(f"[Emulator] Saved TopLeft: {self.topLeftPosition}")

        elif cmd == "RememberBottomRight":
            self.bottomRightPosition = (int(self.virtual_position['x']), int(self.virtual_position['y']))
            logging.info(f"[Emulator] Saved BottomRight: {self.bottomRightPosition}")

        elif cmd == "SwitchLedW" and len(parts) >= 2:
            self.white_led_on = parts[1] == "1"
            logging.info(f"[Emulator] White LED: {'ON' if self.white_led_on else 'OFF'}")
        
        elif cmd == "SwitchLedB" and len(parts) >= 2:
            self.blue_led_on = parts[1] == "1"
            logging.info(f"[Emulator] Blue LED: {'ON' if self.blue_led_on else 'OFF'}")

        return "OK"

    # High-level command methods
    
    def white_led_switch(self, state: bool):
        message = 'SwitchLedW 1' if state else 'SwitchLedW 0'
        self.send(message)

    def blue_led_switch(self, state: bool):
        message = 'SwitchLedB 1' if state else 'SwitchLedB 0'
        self.send(message)

    def delta(self, x: float, y: float, z: float):
        message = f'Delta {x} {y} {z}'
        self.execute_command(message)

    def delta_pump(self, pump_index: int, delta: float):
        message = f'DeltaPump {pump_index} {delta}'
        self.execute_command(message)

    def manifold_delta(self, delta: float):
        message = f'ManifoldDelta {delta}'
        self.execute_command(message)

    def set_position(self, x: float, y: float, z: float):
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
