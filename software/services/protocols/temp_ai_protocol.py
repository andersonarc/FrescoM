from services.protocols.base_protocol import BaseProtocol
from services.fresco_xyz import FrescoXYZ
from services.z_camera import ZCamera
from services.images_storage import ImagesStorage
import math


class SpiralMovementProtocol(BaseProtocol):
    """
    Protocol that moves the FrescoXYZ system in a spiral pattern from corner to center.
    Starts at one corner of the 96-well plate and spirals inward to the center,
    taking images at each position along the spiral path.
    """

    def __init__(self,
                 fresco_xyz: FrescoXYZ,
                 z_camera: ZCamera,
                 images_storage: ImagesStorage):
        super(SpiralMovementProtocol, self).__init__(fresco_xyz=fresco_xyz,
                                                     z_camera=z_camera,
                                                     images_storage=images_storage)
        self.images_storage = images_storage

    def perform(self):
        """
        Execute the spiral movement protocol from corner to center.
        """
        super(SpiralMovementProtocol, self).perform()
        
        print("Starting Spiral Movement Protocol")
        
        # Initialize system
        self.fresco_xyz.white_led_switch(True)
        self.fresco_xyz.go_to_zero()
        
        # Create session folder for images
        session_folder_path = self.images_storage.create_new_session_folder()
        print(f"Created session folder: {session_folder_path}")
        
        # Move to starting corner (top-left corner of plate)
        # Approximate top-left well position
        start_x = -9000  # About -45mm in steps
        start_y = -5600  # About -28mm in steps
        
        print(f"Moving to starting position: ({start_x}, {start_y})")
        self.fresco_xyz.set_position(start_x, start_y, 0)
        self.hold_position(1)
        
        # Take initial image at corner
        self.capture_image_at_position(session_folder_path, 0, "corner")
        
        # Define spiral parameters
        center_x = 0  # Center of plate
        center_y = 0
        max_radius = 10000  # Maximum radius in steps (about 50mm)
        step_size = 400   # Step size for movement (about 2mm)
        angle_increment = 0.3  # Radians to increment each step
        
        # Execute spiral movement
        self.execute_spiral_movement(session_folder_path, center_x, center_y, 
                                   max_radius, step_size, angle_increment)
        
        # Return to center and take final image
        print("Returning to center for final image")
        self.fresco_xyz.go_to_zero()
        self.capture_image_at_position(session_folder_path, 999, "center_final")
        
        # Turn off LED
        self.fresco_xyz.white_led_switch(False)
        print("Spiral Movement Protocol completed")

    def execute_spiral_movement(self, folder_path, center_x, center_y, max_radius, step_size, angle_increment):
        """
        Execute the spiral movement pattern.
        """
        angle = 0
        radius = step_size
        position_index = 1
        
        print("Beginning spiral movement from corner to center")
        
        while radius <= max_radius:
            # Calculate next position in spiral
            target_x = center_x + int(radius * math.cos(angle))
            target_y = center_y + int(radius * math.sin(angle))
            
            # Ensure we stay within reasonable bounds
            target_x = max(-10000, min(10000, target_x))
            target_y = max(-6400, min(6400, target_y))
            
            print(f"Moving to spiral position {position_index}: ({target_x}, {target_y}), radius: {radius:.0f}")
            
            # Move to safe Z height before XY movement
            self.fresco_xyz.go_to_zero_z()
            
            # Move to target position
            self.fresco_xyz.set_position(target_x, target_y, 0)
            self.hold_position(0.5)
            
            # Capture image at this position
            self.capture_image_at_position(folder_path, position_index, "spiral")
            
            # Update spiral parameters
            angle += angle_increment
            radius += step_size * 0.1  # Gradually increase radius
            position_index += 1
            
            # Safety check - limit number of positions
            if position_index > 200:
                print("Reached maximum number of positions, stopping spiral")
                break
        
        print(f"Completed spiral movement with {position_index} positions")

    def capture_image_at_position(self, folder_path, index, prefix):
        """
        Capture and save an image at the current position.
        """
        try:
            # Focus on current position
            self.z_camera.focus_on_current_object()
            self.hold_position(0.5)
            
            # Capture image
            image = self.z_camera.fresco_camera.get_current_image()
            
            # Save image
            image_path = f"{folder_path}/{prefix}_{index:03d}.png"
            self.images_storage.save(image, image_path)
            
            print(f"Captured image: {prefix}_{index:03d}.png")
            
        except Exception as e:
            print(f"Error capturing image at position {index}: {str(e)}")
