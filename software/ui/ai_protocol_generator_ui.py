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
    """Separate AI interface for protocol generation."""

    def __init__(self, master, protocols_performer: ProtocolsPerformer):
        super().__init__(master=master)
        self.protocols_performer = protocols_performer
        self.generated_code = None
        self.last_error = None
        self.conversation_history: List[Dict] = []
        self.init_ui()

    def init_ui(self):
        header = Frame(self)
        header.pack(fill=tk.X, pady=(5, 10))
        
        tk.Label(header, text="AI Protocol Generator", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        tk.Button(header, text="New Conversation", command=self.reset_conversation).pack(side=tk.RIGHT)
        
        # Conversation area
        conv_frame = Frame(self)
        conv_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tk.Label(conv_frame, text="Conversation:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 3))
        
        self.conv_text = scrolledtext.ScrolledText(conv_frame, height=12, wrap=tk.WORD, 
                                                   font=("Arial", 10), bg="#f9f9f9", state=tk.DISABLED)
        self.conv_text.pack(fill=tk.BOTH, expand=True)
        self.conv_text.tag_config("user", foreground="#0066cc", font=("Arial", 10, "bold"))
        self.conv_text.tag_config("assistant", foreground="#00aa00", font=("Arial", 10, "bold"))
        self.conv_text.tag_config("system", foreground="#666666", font=("Arial", 9, "italic"))
        
        # User input
        input_frame = Frame(self)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(input_frame, text="Your message:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        
        self.input_text = scrolledtext.ScrolledText(input_frame, height=3, wrap=tk.WORD, font=("Arial", 10))
        self.input_text.pack(fill=tk.X, pady=(3, 5))
        self.input_text.bind('<Control-Return>', lambda e: self.send_message())
        
        btn_frame = Frame(input_frame)
        btn_frame.pack(fill=tk.X)
        
        self.send_btn = tk.Button(btn_frame, text="Send Message (Ctrl+Enter)", command=self.send_message,
                                  padx=15, pady=5, font=("Arial", 10, "bold"))
        self.send_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.include_examples = tk.BooleanVar(value=True)
        tk.Checkbutton(btn_frame, text="Include examples", 
                      variable=self.include_examples).pack(side=tk.LEFT, padx=10)
        
        self.status = tk.Label(input_frame, text="Ready to start conversation...", fg="blue", font=("Arial", 9))
        self.status.pack(pady=3)
        
        # Generated Code
        code_frame = Frame(self)
        code_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        
        code_header = Frame(code_frame)
        code_header.pack(fill=tk.X)
        
        tk.Label(code_header, text="Generated Code:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, pady=(0, 3))
        
        self.code_text = scrolledtext.ScrolledText(code_frame, height=10, wrap=tk.NONE,
                                                   font=("Consolas", 9), bg="#2b2b2b", fg="#f8f8f2",
                                                   insertbackground="white")
        self.code_text.pack(fill=tk.BOTH, expand=True)
        
        # Action buttons
        action_frame = Frame(self)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.save_btn = tk.Button(action_frame, text="Save Protocol", command=self.save, 
                                 state=tk.DISABLED, width=15)
        self.save_btn.pack(side=tk.LEFT, padx=2)
        
        self.exec_btn = tk.Button(action_frame, text="Execute Protocol", command=self.execute, 
                                 state=tk.DISABLED, width=15)
        self.exec_btn.pack(side=tk.LEFT, padx=2)
        
        # Execution Log
        log_frame = Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 5))
        
        tk.Label(log_frame, text="Execution Log:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 3))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, wrap=tk.WORD,
                                                  font=("Consolas", 8), bg="#f0f0f0")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def add_to_conversation(self, role: str, content: str):
        """Add message to conversation display."""
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
        """Start a new conversation."""
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
        
        self.status.config(text="Ready to start conversation...", fg="blue")
        self.add_to_conversation("system", "New conversation started. Describe the protocol you want to create.")

    def send_message(self):
        """Send user message to Claude."""
        message = self.input_text.get("1.0", tk.END).strip()
        if not message:
            return
        
        self.add_to_conversation("user", message)
        self.conversation_history.append({"role": "user", "content": message})
        self.input_text.delete("1.0", tk.END)
        
        self.send_btn.config(state=tk.DISABLED)
        self.status.config(text="Claude is thinking...", fg="blue")
        
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
                self.after(0, self._on_conversation_response, message)
                
        except Exception as e:
            error_msg = f"{str(e)}\n\nThis usually means Claude's response wasn't in the expected format."
            self.after(0, self._on_error, error_msg)

    def _build_conversational_prompt(self, spec: str, examples: List[tuple]) -> str:
        system_prompt = f"""{spec}

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
- Include docstrings
- Add helpful comments
- Handle errors gracefully
- Follow the template exactly"""

        if examples:
            examples_text = "\n\n## Example Protocols\n"
            for filename, code in examples:
                examples_text += f"\n### {filename}\n```python\n{code}\n```\n"
            system_prompt += examples_text

        conversation_context = "\n\n## Current Conversation\n"
        for msg in self.conversation_history:
            role = msg["role"].capitalize()
            conversation_context += f"{role}: {msg['content']}\n\n"

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
            
            # Strip markdown code blocks
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            elif response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            return json.loads(response_text)
            
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}\nResponse: {response_text}")
            raise ValueError(f"Failed to parse Claude's response as JSON: {str(e)}")
        except Exception as e:
            logging.error(f"Claude API error: {e}")
            raise

    def _on_conversation_response(self, message: str):
        """Handle conversational response from Claude."""
        self.add_to_conversation("assistant", message)
        self.conversation_history.append({"role": "assistant", "content": message})
        
        self.send_btn.config(state=tk.NORMAL)
        self.status.config(text="Ready for your response...", fg="blue")

    def _on_code_generated(self, response: dict):
        """Handle code generation response."""
        self.add_to_conversation("assistant", f"Generated: {response.get('name', 'Protocol')}")
        
        # Validate syntax
        try:
            compile(self.generated_code, '<string>', 'exec')
        except SyntaxError as e:
            self.add_to_conversation("system", f"[WARNING] Syntax error in generated code: {e}")
            self.send_btn.config(state=tk.NORMAL)
            self.status.config(text="Syntax error - please ask Claude to fix it", fg="red")
            return
        
        # Show code
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert("1.0", self.generated_code)
        
        # Enable buttons
        self.save_btn.config(state=tk.NORMAL)
        self.exec_btn.config(state=tk.NORMAL)
        self.send_btn.config(state=tk.NORMAL)
        
        self.status.config(text=f"[SUCCESS] {response.get('name', 'Protocol')} generated", fg="green")
        self.add_to_conversation("system", "[SUCCESS] Code generated! You can now execute it or ask for changes.")

    def _on_error(self, error: str):
        """Handle errors."""
        self.add_to_conversation("system", f"[ERROR] {error}")
        self.send_btn.config(state=tk.NORMAL)
        self.status.config(text="Error occurred", fg="red")

    def log(self, message: str, level: str = "info"):
        """Add message to execution log."""
        colors = {"info": "black", "error": "red", "success": "green"}
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.tag_config(level, foreground=colors.get(level, "black"))
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
        
        _thread.start_new_thread(self._execute_protocol, ())

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

    def _on_execution_error(self, error: str):
        """Handle execution errors."""
        short_error = error.split('\n')[0]
        self.add_to_conversation("system", f"[ERROR] Execution failed: {short_error}")
        
        # Auto-send error to Claude for fixing
        error_message = f"The protocol failed with this error:\n```\n{error}\n```\n\nPlease fix the code."
        
        self.conversation_history.append({"role": "user", "content": error_message})
        self.add_to_conversation("user", f"[Auto-sent error for fixing]\n{short_error}")
        
        self.status.config(text="Asking Claude to fix the error...", fg="blue")
        _thread.start_new_thread(self._process_message, ())

    def save(self):
        """Save protocol to file."""
        if not self.generated_code:
            return
        
        name = simpledialog.askstring("Save", "Filename (without .py):", parent=self)
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

    def _build_spec(self) -> str:
        return """# FrescoM Protocol API

## Coordinates: Steps, not millimeters
- 200 steps = 1mm, 1800 steps = 9mm (one well for 96-well plate)
- Origin (0,0,0) at plate center
- Z-axis: negative=up, positive=down

## Template
```python
from services.protocols.base_protocol import BaseProtocol
import math  # if needed

class MyProtocol(BaseProtocol):
    def __init__(self, fresco_xyz, z_camera, images_storage):
        super().__init__(fresco_xyz, z_camera, images_storage)
    
    def perform(self):
        self.fresco_xyz.white_led_switch(True)
        folder = self.images_storage.create_new_session_folder()
        # Your code here
        
        # Check for stop requests in loops:
        if self.fresco_xyz.should_stop():
            return
```

## Available Methods
**Movement:** `delta(x,y,z)`, `set_position(x,y,z)`, `go_to_zero()`, `go_to_zero_z()`
**Imaging:** `focus_on_current_object()`, `get_current_image()`, `save(image, path)`, `create_new_session_folder()`
**LEDs:** `white_led_switch(True/False)`, `blue_led_switch(True/False)`
**Utility:** `hold_position(seconds)`, `well_step_96=1800`, `plate_size_96=(12,8)`
**Control:** `should_stop()` - check this in loops to allow protocol interruption

## Key Rules
1. All coordinates must be integers - use `int()` when calculating
2. Negative Z = up, positive Z = down
3. Check `should_stop()` in long loops"""

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
