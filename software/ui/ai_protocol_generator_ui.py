import tkinter as tk
from services.protocols_performer import ProtocolsPerformer
from tkinter.ttk import Frame
from tkinter import scrolledtext, messagebox, simpledialog
import _thread
import json
import re
import traceback
from typing import List, Dict
from anthropic import Anthropic
import logging


class AIProtocolGeneratorUI(Frame):

    def __init__(self, master, protocols_performer: ProtocolsPerformer):
        super().__init__(master=master)
        self.protocols_performer = protocols_performer
        self.generated_code = None
        self.generated_protocol_name = None
        self.last_error = None
        self.conversation_history: List[Dict] = []
        self.init_ui()

    def init_ui(self):
        header = Frame(self)
        header.pack(fill=tk.X, pady=(5, 10))
        
        tk.Label(header, text="Protocol Generator", font=("Arial", 12)).pack(side=tk.LEFT)
        tk.Button(header, text="Load", command=self.load_conversation).pack(side=tk.RIGHT, padx=2)
        tk.Button(header, text="Save", command=self.save_conversation).pack(side=tk.RIGHT, padx=2)
        tk.Button(header, text="New", command=self.reset_conversation).pack(side=tk.RIGHT, padx=2)

        conv_frame = Frame(self)
        conv_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(conv_frame, text="Conversation:", font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 3))

        self.conv_text = scrolledtext.ScrolledText(conv_frame, height=12, wrap=tk.WORD,
                                                   font=("Arial", 10), state=tk.DISABLED)
        self.conv_text.pack(fill=tk.BOTH, expand=True)
        self.conv_text.tag_config("user", font=("Arial", 10))
        self.conv_text.tag_config("assistant", font=("Arial", 10))
        self.conv_text.tag_config("system", font=("Arial", 9, "italic"))
        
        # User input
        input_frame = Frame(self)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(input_frame, text="Your message:", font=("Arial", 10)).pack(anchor=tk.W)

        self.input_text = scrolledtext.ScrolledText(input_frame, height=3, wrap=tk.WORD, font=("Arial", 10))
        self.input_text.pack(fill=tk.X, pady=(3, 5))
        self.input_text.bind('<Control-Return>', lambda e: self.send_message())

        btn_frame = Frame(input_frame)
        btn_frame.pack(fill=tk.X)

        self.send_btn = tk.Button(btn_frame, text="Send Message (Ctrl+Enter)", command=self.send_message,
                                  padx=15, pady=5, font=("Arial", 10))
        self.send_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.include_examples = tk.BooleanVar(value=True)
        tk.Checkbutton(btn_frame, text="Include examples",
                      variable=self.include_examples).pack(side=tk.LEFT, padx=10)

        self.auto_fix_errors = tk.BooleanVar(value=True)
        tk.Checkbutton(btn_frame, text="Automatic error fixing",
                      variable=self.auto_fix_errors).pack(side=tk.LEFT, padx=10)

        self.status = tk.Label(input_frame, text="Ready to start conversation...", font=("Arial", 9))
        self.status.pack(pady=3)
        
        # Generated Code
        code_frame = Frame(self)
        code_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        
        code_header = Frame(code_frame)
        code_header.pack(fill=tk.X)
        
        tk.Label(code_header, text="Generated Code:", font=("Arial", 10)).pack(side=tk.LEFT, pady=(0, 3))

        self.code_text = scrolledtext.ScrolledText(code_frame, height=10, wrap=tk.NONE,
                                                   font=("Consolas", 9))
        self.code_text.pack(fill=tk.BOTH, expand=True)

        action_frame = Frame(self)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        self.save_btn = tk.Button(action_frame, text="Save Protocol", command=self.save,
                                 state=tk.DISABLED, width=15)
        self.save_btn.pack(side=tk.LEFT, padx=2)

        self.exec_btn = tk.Button(action_frame, text="Execute Protocol", command=self.execute,
                                 state=tk.DISABLED, width=15)
        self.exec_btn.pack(side=tk.LEFT, padx=2)

        self.stop_btn = tk.Button(action_frame, text="Stop", command=self.stop_execution,
                                 state=tk.DISABLED, width=10)
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        log_frame = Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 5))

        tk.Label(log_frame, text="Execution Log:", font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 3))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, wrap=tk.WORD,
                                                  font=("Consolas", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def add_to_conversation(self, role: str, content: str):
        self.conv_text.config(state=tk.NORMAL)
        
        if role == "user":
            self.conv_text.insert(tk.END, "You: ", "user")
        elif role == "assistant":
            self.conv_text.insert(tk.END, "Claude: ", "assistant")
        else:
            self.conv_text.insert(tk.END, "[System] ", "system")
        
        self.conv_text.insert(tk.END, f"{content}\n\n")
        self.conv_text.see(tk.END)
        self.conv_text.config(state=tk.DISABLED)

    def reset_conversation(self):
        if self.conversation_history and not messagebox.askyesno("New Conversation", 
                                                                 "Start a new conversation? Current progress will be lost."):
            return
        
        self.conversation_history = []
        self.generated_code = None
        self.last_error = None
        
        self.conv_text.config(state=tk.NORMAL)
        self.conv_text.delete("1.0", tk.END)
        self.conv_text.config(state=tk.DISABLED)
        
        self.code_text.delete("1.0", tk.END)
        self.input_text.delete("1.0", tk.END)
        
        self.save_btn.config(state=tk.DISABLED)
        self.exec_btn.config(state=tk.DISABLED)
        
        self.status.config(text="Ready to start conversation...")
        self.add_to_conversation("system", "New conversation started. Describe the protocol you want to create.")

    def save_conversation(self):
        if not self.conversation_history:
            messagebox.showwarning("No Conversation", "No conversation to save.")
            return

        filename = simpledialog.askstring("Save Conversation", "Filename (without .json):", parent=self)
        if filename:
            if not filename.endswith('.json'):
                filename += '.json'

            path = f"{self.protocols_performer.protocols_folder_path}/{filename}"
            try:
                with open(path, 'w') as f:
                    json.dump({
                        'conversation_history': self.conversation_history,
                        'generated_code': self.generated_code
                    }, f, indent=2)
                messagebox.showinfo("Saved", f"Conversation saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def load_conversation(self):
        filename = simpledialog.askstring("Load Conversation", "Filename (without .json):", parent=self)
        if filename:
            if not filename.endswith('.json'):
                filename += '.json'

            path = f"{self.protocols_performer.protocols_folder_path}/{filename}"
            try:
                with open(path, 'r') as f:
                    data = json.load(f)

                self.conversation_history = data.get('conversation_history', [])
                self.generated_code = data.get('generated_code')

                self.conv_text.config(state=tk.NORMAL)
                self.conv_text.delete("1.0", tk.END)
                self.conv_text.config(state=tk.DISABLED)

                for msg in self.conversation_history:
                    self.add_to_conversation(msg['role'], msg['content'])

                if self.generated_code:
                    self.code_text.delete("1.0", tk.END)
                    self.code_text.insert("1.0", self.generated_code)
                    self.save_btn.config(state=tk.NORMAL)
                    self.exec_btn.config(state=tk.NORMAL)

                messagebox.showinfo("Loaded", f"Conversation loaded from {filename}")
            except FileNotFoundError:
                messagebox.showerror("Error", f"File not found: {filename}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def send_message(self):
        message = self.input_text.get("1.0", tk.END).strip()
        if not message:
            return
        
        self.add_to_conversation("user", message)
        self.conversation_history.append({"role": "user", "content": message})
        self.input_text.delete("1.0", tk.END)
        
        self.send_btn.config(state=tk.DISABLED)
        self.status.config(text="Claude is thinking...")
        
        _thread.start_new_thread(self._process_message, ())

    def _process_message(self):
        """Process message in background thread."""
        try:
            spec = self._build_spec()
            examples = self._get_example_protocols() if self.include_examples.get() else []
            
            prompt = self._build_conversational_prompt(spec, examples)
            response = self._call_claude_conversation(prompt)
            
            if not isinstance(response, dict):
                raise ValueError("Response is not a dictionary")
            
            if response.get("ready_to_generate") and "code" in response:
                self.generated_code = response["code"]
                self.after(0, self._on_code_generated, response)
            else:
                message = response.get("message", "I'm here to help! What would you like to do?")
                is_non_json = response.get("non_json_response", False)
                self.after(0, self._on_conversation_response, message, is_non_json)
                
        except Exception as e:
            error_msg = f"{str(e)}\n\nThis usually means Claude's response wasn't in the expected format."
            self.after(0, self._on_error, error_msg)

    def _build_conversational_prompt(self, spec: str, examples: List[tuple]) -> str:
        json_reminder = ""
        if self.conversation_history and len(self.conversation_history) >= 2:
            last_assistant = None
            for msg in reversed(self.conversation_history):
                if msg["role"] == "assistant":
                    last_assistant = msg
                    break
            if last_assistant and "non_json_response" in last_assistant:
                json_reminder = "\n\nIMPORTANT: Please respond in valid JSON format as specified below.\n"

        system_prompt = f"""{spec}{json_reminder}

## Your Role
You are an assistant helping users create protocols for the FrescoM microscope robot.

## Conversation Guidelines
1. Ask clarifying questions if the user's request is vague or missing critical details
2. Discuss the approach before generating code
3. Only generate code when you have all necessary information
4. If there's an error, help debug and fix it

## Key Information to Gather
Before generating code, ensure you know:
- What movements are needed (which wells, positions)
- What images to capture (how many, which wells)
- Perfusion requirements (which pumps, volumes, timing)
- Any specific timing or sequencing requirements

## Response Format
Respond with JSON:
```json
{{
  "ready_to_generate": false,
  "message": "Your response to the user"
}}
```

When you have all information and are ready to generate code:
```json
{{
  "ready_to_generate": true,
  "name": "ProtocolName",
  "description": "Brief description",
  "code": "Complete Python code here"
}}
```

## Code Requirements
- Use int() for all coordinates
- Follow the template exactly
- Handle errors gracefully"""

        if examples:
            examples_text = "\n\n## Example Protocols\n"
            for filename, code in examples:
                examples_text += f"\n### {filename}\n```python\n{code}\n```\n"
            system_prompt += examples_text

        conversation_context = "\n\n## Current Conversation\n"
        for msg in self.conversation_history:
            role = msg["role"].capitalize()
            content = msg["content"]
            if "non_json_response" not in msg:
                conversation_context += f"{role}: {content}\n\n"

        return system_prompt + conversation_context

    def _call_claude_conversation(self, prompt: str) -> dict:
        """Call Claude API for conversational protocol generation."""
        try:
            client = Anthropic()

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text

            import re
            json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1).strip()
            else:
                json_text = response_text.strip()
                if json_text.startswith("```json"):
                    json_text = json_text[7:]
                elif json_text.startswith("```"):
                    json_text = json_text[3:]
                if json_text.endswith("```"):
                    json_text = json_text[:-3]
                json_text = json_text.strip()

            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                return {
                    "ready_to_generate": False,
                    "message": response_text,
                    "non_json_response": True
                }

        except Exception as e:
            logging.error(f"Claude API error: {e}")
            raise

    def _on_conversation_response(self, message: str, is_non_json: bool = False):
        """Handle conversational response from Claude."""
        self.add_to_conversation("assistant", message)
        self.conversation_history.append({"role": "assistant", "content": message})

        if is_non_json:
            self.add_to_conversation("system", "[Note: Response was not in JSON format - reminder sent to Claude]")

        self.send_btn.config(state=tk.NORMAL)
        self.status.config(text="Ready for your response...", )

    def _on_code_generated(self, response: dict):
        self.add_to_conversation("assistant", f"Generated: {response.get('name', 'Protocol')}")

        # Store protocol name for default filename
        self.generated_protocol_name = response.get('name', 'Protocol')

        # Validate syntax
        try:
            compile(self.generated_code, '<string>', 'exec')
        except SyntaxError as e:
            self.add_to_conversation("system", f"[WARNING] Syntax error in generated code: {e}")
            self.send_btn.config(state=tk.NORMAL)
            self.status.config(text="Syntax error - please ask Claude to fix it", )
            return

        # Show code
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", self.generated_code)

        # Enable buttons
        self.save_btn.config(state=tk.NORMAL)
        self.exec_btn.config(state=tk.NORMAL)
        self.send_btn.config(state=tk.NORMAL)

        self.status.config(text=f"[SUCCESS] {response.get('name', 'Protocol')} generated", )
        self.add_to_conversation("system", "[SUCCESS] Code generated! You can now execute it or ask for changes.")

    def _on_error(self, error: str):
        self.add_to_conversation("system", f"[ERROR] {error}")
        self.send_btn.config(state=tk.NORMAL)
        self.status.config(text="Error occurred", )

    def log(self, message: str, level: str = "info"):
        color = {"error": "red", "success": "green", "info": "black"}.get(level, "black")
        self.log_text.insert(tk.END, f"{message}\n", (color,))
        self.log_text.tag_config("red", foreground="red")
        self.log_text.tag_config("green", foreground="green")
        self.log_text.tag_config("black", foreground="black")
        self.log_text.see(tk.END)
        self.log_text.update()

    def execute(self):
        """Execute the generated protocol."""
        if not self.generated_code:
            return

        if not messagebox.askyesno("Execute", "Execute this protocol?\n\n[WARNING] This will move the robot!"):
            return

        self.log_text.delete("1.0", tk.END)
        self.log("Starting protocol execution...")
        self.last_error = None

        self.exec_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        _thread.start_new_thread(self._execute_protocol, ())

    def stop_execution(self):
        """Request protocol to stop."""
        if messagebox.askyesno("Stop Protocol", "Stop the current protocol?\n\nThe protocol will stop at the next checkpoint."):
            self.protocols_performer.fresco_xyz.request_stop()
            self.log("[STOP REQUESTED] Protocol will stop at next checkpoint...")
            self.stop_btn.config(state=tk.DISABLED)

    def _execute_protocol(self):
        """Execute protocol in background thread."""
        try:
            # Reset stop flag
            self.protocols_performer.fresco_xyz.reset_stop_flag()
            
            namespace = {}
            from services.protocols.base_protocol import BaseProtocol
            namespace['BaseProtocol'] = BaseProtocol
            
            exec(self.generated_code, namespace)
            
            protocol_class = None
            for name, obj in namespace.items():
                if isinstance(obj, type) and issubclass(obj, BaseProtocol) and obj != BaseProtocol:
                    protocol_class = obj
                    break
            
            if protocol_class is None:
                raise Exception("No protocol class found")
            
            protocol = protocol_class(
                self.protocols_performer.fresco_xyz,
                self.protocols_performer.z_camera,
                self.protocols_performer.images_storage
            )
            protocol.perform()
            
            if self.protocols_performer.fresco_xyz.should_stop():
                self.after(0, lambda: self.log("[STOPPED] Protocol stopped by user", "info"))
                self.after(0, lambda: self.add_to_conversation("system", "[STOPPED] Protocol stopped by user"))
            else:
                self.after(0, lambda: self.log("[SUCCESS] Protocol completed successfully!", "success"))
                self.after(0, lambda: self.add_to_conversation("system", "[SUCCESS] Protocol executed successfully!"))
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            self.last_error = error_msg
            self.after(0, lambda: self.log(f"[ERROR] Protocol failed:\n{error_msg}", "error"))
            self.after(0, lambda: self._on_execution_error(error_msg))
        finally:
            self.after(0, lambda: self.exec_btn.config(state=tk.NORMAL))
            self.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))

    def _on_execution_error(self, error: str):
        """Handle execution errors."""
        short_error = error.split('\n')[0]
        self.add_to_conversation("system", f"[ERROR] Execution failed: {short_error}")

        if self.auto_fix_errors.get():
            error_message = f"The protocol failed with this error:\n```\n{error}\n```\n\nPlease fix the code."

            self.conversation_history.append({"role": "user", "content": error_message})
            self.add_to_conversation("user", f"[Auto-sent error for fixing]\n{short_error}")

            self.status.config(text="Asking Claude to fix the error...", )
            _thread.start_new_thread(self._process_message, ())

    def save(self):
        if not self.generated_code:
            return

        # Convert PascalCase protocol name to snake_case for filename
        default_name = self._to_snake_case(self.generated_protocol_name) if self.generated_protocol_name else "my_protocol"

        name = simpledialog.askstring("Save", "Filename (without .py):", parent=self, initialvalue=default_name)
        if name:
            if not name.endswith('.py'):
                name += '.py'
            path = f"{self.protocols_performer.protocols_folder_path}/{name}"

            try:
                with open(path, 'w') as f:
                    f.write(self.generated_code)
                self.log(f"Saved to {name}", "success")
                self.add_to_conversation("system", f"[SUCCESS] Saved as {name}")
            except Exception as e:
                self.log(f"Save error: {e}", "error")
                messagebox.showerror("Error", str(e))

    def _to_snake_case(self, name: str) -> str:
        import re
        # Insert underscore before uppercase letters (except at start)
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        # Insert underscore before uppercase letters followed by lowercase
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _get_plate_info(self) -> str:
        xyz = self.protocols_performer.fresco_xyz
        if xyz and xyz.plate:
            cfg = xyz.plate
            return f"""- Plate type: {xyz.plate.get('name', 'Unknown')}
- Rows: {cfg['rows']} (labeled {cfg['row_labels'][0]}-{cfg['row_labels'][-1]})
- Columns: {cfg['cols']} (labeled 1-{cfg['cols']})
- Well spacing: {cfg['well_spacing']} mm ({cfg['steps_per_well']} steps)
- Well diameter: {cfg['well_diameter']} mm
- Well depth: {cfg['well_depth']} mm
- Bottom-left position (steps): {cfg['bottom_left']}
- Top-right position (steps): {cfg['top_right']}"""
        return "Plate info not available"

    def _build_spec(self) -> str:
        plate_info = self._get_plate_info()
        return f"""# FrescoM Protocol API

## Coordinate System
- 200 steps = 1mm
- Plate-relative coordinates: (0,0) is ALWAYS the bottom-left well (A1)
- Z-axis: negative=up, positive=down
- Plate calibration is handled automatically - all movement methods account for it
- Use any movement method freely - set_position(), delta(), or helper methods all work

## Current Plate Configuration
{plate_info}

## Template
```python
from services.protocols.base_protocol import BaseProtocol
import math

class MyProtocol(BaseProtocol):
    def __init__(self, fresco_xyz, z_camera, images_storage):
        super().__init__(fresco_xyz, z_camera, images_storage)

    def perform(self):
        self.fresco_xyz.white_led_switch(True)
        folder = self.images_storage.create_new_session_folder()

        # Example 1: Using helper method to visit all wells
        for row in range(self.plate_rows):
            for col in range(self.plate_cols):
                self.move_to_well(row, col)  # row 0 = A, col 0 = 1
                # Do something...
                self.check_pause_stop()

        # Example 2: Using absolute positioning
        self.fresco_xyz.set_position(0, 0, -2000)  # Go to A1 at z=-2000

        # Example 3: Using relative movement
        self.fresco_xyz.delta(self.well_spacing_steps, 0, 0)  # Move one well right

        if self.fresco_xyz.should_stop():
            return
```

## Available Methods

**Movement (self.fresco_xyz) - All methods handle calibration automatically:**
- `self.fresco_xyz.set_position(x_steps, y_steps, z_steps)` - Move to plate-relative position
- `self.fresco_xyz.delta(x_steps, y_steps, z_steps)` - Move relative to current position
- `self.fresco_xyz.go_to_zero()` - Return to (0,0) bottom-left well at safe height
- `self.fresco_xyz.go_to_zero_z()` - Raise Z to safe height

**Well Navigation Helpers (from BaseProtocol) - Convenient for well-based protocols:**
- `self.move_to_well(row, col, z=None)` - Move to specific well by row/col indices
- `self.get_well_position(row, col, z=None)` - Get (x, y, z) position for a well

**Pumps (self.fresco_xyz):**
- `self.fresco_xyz.delta_pump(pump_index, delta_steps)` - pump_index 0-7, positive=dispense, negative=aspirate
- `self.fresco_xyz.manifold_delta(delta_steps)` - move manifold up/down
- `self.fresco_xyz.go_to_zero_manifold()` - return manifold to zero position

**Imaging (self.z_camera):**
- `self.z_camera.focus_on_current_object()` - autofocus at current position
- `self.z_camera.fresco_camera.get_current_image()` - capture image (returns numpy array)

**Image Storage (self.images_storage):**
- `self.images_storage.save(image, path)` - save image to file
- `self.images_storage.create_new_session_folder()` - create timestamped folder (returns path string)

**LEDs (self.fresco_xyz):**
- `self.fresco_xyz.white_led_switch(True/False)` - white LED on/off
- `self.fresco_xyz.blue_led_switch(True/False)` - blue LED on/off

**Timing & Control (self):**
- `self.hold_position(seconds)` - wait and check for pause/stop
- `self.check_pause_stop()` - check if user paused/stopped protocol
- `self.fresco_xyz.should_stop()` - returns True if stop requested

**Plate Info (from BaseProtocol):**
- `self.plate_rows` - number of rows (e.g. 8 for 96-well)
- `self.plate_cols` - number of columns (e.g. 12 for 96-well)
- `self.well_spacing_mm` - distance between wells in mm
- `self.well_spacing_steps` - distance between wells in steps

## Protocol Interruption
Users can pause or stop protocols during execution:
- PAUSE: Protocol waits until resumed (handled by `check_pause_stop()` and `hold_position()`)
- STOP: Protocol should exit cleanly (check `should_stop()` in loops)
- Always call `check_pause_stop()` after long operations
- Always check `should_stop()` in loops

## Key Rules
1. All coordinates must be integers - use `int()` when calculating
2. Negative Z = up, positive Z = down
3. Plate-relative coordinates: (0,0) = bottom-left well (A1)
4. Well indices are 0-based: row 0 = A, row 1 = B, etc.; col 0 = 1, col 1 = 2, etc.
5. Check `should_stop()` and call `check_pause_stop()` regularly in loops
6. Use any movement method freely - all handle calibration automatically"""

    def _get_example_protocols(self) -> List[tuple]:
        examples = []
        
        try:
            base_path = "./services/protocols/base_protocol.py"
            with open(base_path, 'r') as f:
                examples.append(("base_protocol.py", f.read()))
        except:
            pass
        
        protocols = self.protocols_performer.available_protocols()
        for p in protocols[:1]:
            try:
                with open(p, 'r') as f:
                    filename = p.split('/')[-1]
                    examples.append((filename, f.read()))
            except:
                pass
        
        return examples
