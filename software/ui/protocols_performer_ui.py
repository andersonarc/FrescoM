import tkinter as tk
from services.protocols_performer import ProtocolsPerformer
from tkinter.ttk import Frame, Combobox, Notebook
from tkinter import scrolledtext, messagebox, simpledialog
import _thread
import json
import re
import traceback
from typing import List, Dict
from anthropic import Anthropic


class ProtocolsPerformerUI(Frame):

    def __init__(self, master, protocols_performer: ProtocolsPerformer):
        super().__init__(master=master)
        self.protocols_performer = protocols_performer
        self.protocols_combobox: Combobox = None
        self.generated_code = None
        self.last_error = None
        self.conversation_history: List[Dict] = []
        self.init_ui()

    def init_ui(self):
        self.master.geometry("950x850")
        
        header = Frame(self)
        header.pack(fill=tk.X, pady=(5, 10))
        
        tk.Label(header, text="Protocol Generator", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        tk.Button(header, text="New Conversation", command=self.reset_conversation).pack(side=tk.RIGHT)
        
        notebook = Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        gen_tab = Frame(notebook)
        notebook.add(gen_tab, text="Generate")
        self._build_generate_tab(gen_tab)
        
        existing_tab = Frame(notebook)
        notebook.add(existing_tab, text="Existing Protocols")
        self._build_existing_tab(existing_tab)

    def _build_generate_tab(self, parent):
        # Conversation area
        conv_frame = Frame(parent)
        conv_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tk.Label(conv_frame, text="Conversation:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 3))
        
        self.conv_text = scrolledtext.ScrolledText(conv_frame, height=12, wrap=tk.WORD, 
                                                   font=("Arial", 10), bg="#f9f9f9", state=tk.DISABLED)
        self.conv_text.pack(fill=tk.BOTH, expand=True)
        self.conv_text.tag_config("user", foreground="#0066cc", font=("Arial", 10, "bold"))
        self.conv_text.tag_config("assistant", foreground="#00aa00", font=("Arial", 10, "bold"))
        self.conv_text.tag_config("system", foreground="#666666", font=("Arial", 9, "italic"))
        
        # User input
        input_frame = Frame(parent)
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
        
        # Generated Code (collapsible)
        code_frame = Frame(parent)
        code_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        
        code_header = Frame(code_frame)
        code_header.pack(fill=tk.X)
        
        tk.Label(code_header, text="Generated Code:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, pady=(0, 3))
        
        self.code_text = scrolledtext.ScrolledText(code_frame, height=10, wrap=tk.NONE,
                                                   font=("Consolas", 9), bg="#2b2b2b", fg="#f8f8f2",
                                                   insertbackground="white")
        self.code_text.pack(fill=tk.BOTH, expand=True)
        
        # Action buttons
        action_frame = Frame(parent)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.save_btn = tk.Button(action_frame, text="Save Protocol", command=self.save, 
                                 state=tk.DISABLED, width=15)
        self.save_btn.pack(side=tk.LEFT, padx=2)
        
        self.exec_btn = tk.Button(action_frame, text="Execute Protocol", command=self.execute, 
                                 state=tk.DISABLED, width=15)
        self.exec_btn.pack(side=tk.LEFT, padx=2)
        
        # Execution Log
        log_frame = Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 5))
        
        tk.Label(log_frame, text="Execution Log:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 3))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, wrap=tk.WORD,
                                                  font=("Consolas", 8), bg="#f0f0f0")
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _build_existing_tab(self, parent):
        tk.Label(parent, text="Select Protocol:", font=("Arial", 10, "bold")).pack(anchor=tk.W, 
                                                                                    padx=5, pady=(5, 3))
        
        proto_frame = Frame(parent)
        proto_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        list_of_protocols = self.protocols_performer.available_protocols()
        self.protocols_combobox = Combobox(proto_frame, width=50, state="readonly", font=("Arial", 9))
        self.protocols_combobox['values'] = list_of_protocols
        if list_of_protocols:
            self.protocols_combobox.current(0)
        self.protocols_combobox.pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Button(proto_frame, text="Refresh", command=self.refresh, width=10).pack(side=tk.LEFT)
        
        tk.Button(parent, text="Run Selected Protocol", command=self.start_protocol, 
                 padx=15, pady=5).pack(padx=5, pady=10)

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
        
        # Add to conversation display
        self.add_to_conversation("user", message)
        
        # Add to history
        self.conversation_history.append({"role": "user", "content": message})
        
        # Clear input
        self.input_text.delete("1.0", tk.END)
        
        # Disable send while processing
        self.send_btn.config(state=tk.DISABLED)
        self.status.config(text="Claude is thinking...", fg="blue")
        
        # Process in background
        _thread.start_new_thread(self._process_message, ())

    def _process_message(self):
        """Process the conversation and get Claude's response."""
        try:
            spec = self._build_spec()
            examples = self._get_example_protocols() if self.include_examples.get() else []
            
            prompt = self._build_conversational_prompt(spec, examples)
            response = self._call_claude_conversation(prompt)
            
            # Validate response structure
            if not isinstance(response, dict):
                raise ValueError("Response is not a dictionary")
            
            # Check if Claude generated code or is asking questions
            if response.get("ready_to_generate") and "code" in response:
                # Code was generated
                self.generated_code = response["code"]
                self.after(0, self._on_code_generated, response)
            else:
                # Claude is asking questions or discussing
                message = response.get("message", "I'm here to help! What would you like to do?")
                self.after(0, self._on_conversation_response, message)
                
        except Exception as e:
            error_msg = f"{str(e)}\n\nThis usually means Claude's response wasn't in the expected format."
            self.after(0, self._on_error, error_msg)

    def _build_conversational_prompt(self, spec: str, examples: List[tuple]) -> str:
        """Build prompt for conversational interaction."""
        system_prompt = f"""{spec}

## Your Role
You are an assistant helping users create protocols for the FrescoM microscope robot. 

## Conversation Guidelines
1. **Ask clarifying questions** if the user's request is vague or missing critical details
2. **Discuss the approach** before generating code
3. **Only generate code** when you have all necessary information
4. **If there's an error**, help debug and fix it

## Key Information to Gather
Before generating code, ensure you know:
- What movements are needed (which wells? what pattern?)
- Whether imaging is needed (at which positions?)
- Any special timing or sequencing requirements
- Expected behavior and outputs

"""
        
        if examples:
            system_prompt += "\n## Example Protocols\n"
            for filename, code in examples[:1]:  # Just include one example
                system_prompt += f"```python\n{code}\n```\n\n"
        
        system_prompt += """
## Response Format
**YOU MUST ALWAYS respond with valid JSON, no matter what. Never respond with plain text.**

You can respond in two ways:

### If asking questions or discussing:
```json
{
    "message": "Your question or discussion",
    "ready_to_generate": false
}
```

### If ready to generate code:
```json
{
    "message": "Brief explanation of what you're generating",
    "ready_to_generate": true,
    "name": "ProtocolClassName",
    "code": "complete Python code"
}
```

**CRITICAL: Your ENTIRE response must be valid JSON. No text before or after the JSON.**

Only generate code when you're confident you understand the requirements!
"""
        
        # Build conversation
        conversation = [{"role": "user", "content": system_prompt}]
        conversation.extend(self.conversation_history)
        
        return conversation

    def _call_claude_conversation(self, messages: List[Dict]) -> dict:
        """Call Claude API with conversation history."""
        client = Anthropic()
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            thinking={
                "type": "enabled",
                "budget_tokens": 2000
            },
            messages=messages
        )
        
        # Extract text response
        text = ""
        for block in message.content:
            if block.type == "text":
                text = block.text.strip()
                break
        
        # Clean up JSON markers
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text).strip()
        
        # Try to parse as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Claude responded with plain text instead of JSON
            # Wrap it in the expected format
            return {
                "message": text,
                "ready_to_generate": False
            }

    def _on_conversation_response(self, message: str):
        """Handle Claude's conversational response."""
        self.conversation_history.append({"role": "assistant", "content": message})
        self.add_to_conversation("assistant", message)
        
        self.send_btn.config(state=tk.NORMAL)
        self.status.config(text="Waiting for your response...", fg="blue")

    def _on_code_generated(self, response: dict):
        """Handle code generation."""
        # Add message to conversation
        msg = response.get("message", "Generated protocol code.")
        self.conversation_history.append({"role": "assistant", "content": msg})
        self.add_to_conversation("assistant", msg)
        
        # Validate syntax
        try:
            compile(self.generated_code, '<string>', 'exec')
        except SyntaxError as e:
            self.add_to_conversation("system", f"⚠️ Syntax error in generated code: {e}")
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
        
        self.status.config(text=f"✓ {response.get('name', 'Protocol')} generated", fg="green")
        self.add_to_conversation("system", "✓ Code generated! You can now execute it or ask for changes.")

    def _on_error(self, error: str):
        """Handle errors."""
        self.add_to_conversation("system", f"❌ Error: {error}")
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
        
        if not messagebox.askyesno("Execute", "Execute this protocol?\n\n⚠️ This will move the robot!"):
            return
        
        self.log_text.delete("1.0", tk.END)
        self.log("Starting protocol execution...")
        self.last_error = None
        
        _thread.start_new_thread(self._execute_protocol, ())

    def _execute_protocol(self):
        """Execute protocol in background thread."""
        try:
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
            
            self.after(0, lambda: self.log("✓ Protocol completed successfully!", "success"))
            self.after(0, lambda: self.add_to_conversation("system", "✓ Protocol executed successfully!"))
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            self.last_error = error_msg
            self.after(0, lambda: self.log(f"❌ Protocol failed:\n{error_msg}", "error"))
            self.after(0, lambda: self._on_execution_error(error_msg))

    def _on_execution_error(self, error: str):
        """Handle execution errors."""
        # Add error to conversation
        short_error = error.split('\n')[0]  # First line only
        self.add_to_conversation("system", f"❌ Execution failed: {short_error}")
        
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
                self.refresh()
                self.log(f"Saved to {name}", "success")
                self.add_to_conversation("system", f"✓ Saved as {name}")
            except Exception as e:
                self.log(f"Save error: {e}", "error")
                messagebox.showerror("Error", str(e))

    def _build_spec(self) -> str:
        return """# FrescoM Protocol API

## Coordinates: Steps, not millimeters
- 200 steps = 1mm, 1800 steps = 9mm (one well)
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
```

## Available Methods
**Movement:** `delta(x,y,z)`, `set_position(x,y,z)`, `go_to_zero()`, `go_to_zero_z()`
**Imaging:** `focus_on_current_object()`, `get_current_image()`, `save(image, path)`, `create_new_session_folder()`
**LEDs:** `white_led_switch(True/False)`, `blue_led_switch(True/False)`
**Utility:** `hold_position(seconds)`, `well_step_96=1800`, `plate_size_96=(12,8)`

## Key Rules
1. All coordinates must be integers - use `int()` when calculating
2. Negative Z = up, positive Z = down"""

    def _get_example_protocols(self) -> List[tuple]:
        examples = []
        
        try:
            base_path = "./services/protocols/base_protocol.py"
            with open(base_path, 'r') as f:
                examples.append(("base_protocol.py", f.read()))
        except:
            pass
        
        protocols = self.protocols_performer.available_protocols()
        for p in protocols[:1]:  # Just one example
            try:
                with open(p, 'r') as f:
                    filename = p.split('/')[-1]
                    examples.append((filename, f.read()))
            except:
                pass
        
        return examples

    def start_protocol(self):
        selected = self.protocols_combobox.get()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a protocol")
            return
        
        try:
            _thread.start_new_thread(self.protocols_performer.perform_protocol, (selected,))
            messagebox.showinfo("Running", f"Protocol started:\n{selected}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def refresh(self):
        protocols = self.protocols_performer.available_protocols()
        self.protocols_combobox['values'] = protocols
        if protocols:
            self.protocols_combobox.current(len(protocols) - 1)
