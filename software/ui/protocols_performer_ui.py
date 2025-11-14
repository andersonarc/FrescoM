import tkinter as tk
from services.protocols_performer import ProtocolsPerformer
from tkinter.ttk import Frame, Combobox, Notebook
from tkinter import scrolledtext, messagebox
import _thread


class ProtocolsPerformerUI(Frame):

    def __init__(self, master, protocols_performer: ProtocolsPerformer):
        super().__init__(master=master)
        self.protocols_performer = protocols_performer
        self.protocols_combobox: Combobox = None
        self.init_ui()

    def init_ui(self):
        self.master.geometry("600x400")
        
        header = Frame(self)
        header.pack(fill=tk.X, pady=(5, 10))
        
        tk.Label(header, text="Protocol Performer", font=("Arial", 12)).pack(side=tk.LEFT)
        tk.Button(header, text="Stop Protocol", command=self.stop_protocol).pack(side=tk.RIGHT, padx=5)
        tk.Button(header, text="Refresh List", command=self.refresh).pack(side=tk.RIGHT)
        
        # Protocol selection
        select_frame = Frame(self)
        select_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(select_frame, text="Select Protocol:", font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))
        
        list_of_protocols = self.protocols_performer.available_protocols()
        self.protocols_combobox = Combobox(select_frame, width=70, state="readonly", font=("Arial", 9))
        self.protocols_combobox['values'] = list_of_protocols
        if list_of_protocols:
            self.protocols_combobox.current(0)
        self.protocols_combobox.pack(fill=tk.X)
        
        # Run button
        btn_frame = Frame(self)
        btn_frame.pack(pady=15)
        
        self.run_btn = tk.Button(btn_frame, text="Run Protocol", command=self.start_protocol,
                                 font=("Arial", 10), padx=20, pady=10)
        self.run_btn.pack()

        # Status
        self.status_label = tk.Label(self, text="Ready", font=("Arial", 9))
        self.status_label.pack(pady=5)
        
        # Execution log
        log_frame = Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 10))
        
        tk.Label(log_frame, text="Execution Log:", font=("Arial", 10)).pack(anchor=tk.W, pady=(0, 5))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD,
                                                  font=("Consolas", 9), bg="#f0f0f0")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config("info", foreground="black")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")

    def log(self, message: str, level: str = "info"):
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.see(tk.END)
        self.log_text.update()

    def start_protocol(self):
        selected = self.protocols_combobox.get()
        if not selected:
            messagebox.showwarning("No selection", "Please select a protocol")
            return
        
        if not messagebox.askyesno("Execute", f"Run protocol?\n\n{selected}\n\n[WARNING] This will move the robot!"):
            return
        
        self.log_text.delete("1.0", tk.END)
        self.log(f"Starting protocol: {selected}")
        self.status_label.config(text="Running...", fg="orange")
        self.run_btn.config(state=tk.DISABLED)
        
        # Reset stop flag
        self.protocols_performer.fresco_xyz.reset_stop_flag()
        
        _thread.start_new_thread(self._run_protocol_thread, (selected,))

    def _run_protocol_thread(self, protocol_path: str):
        """Run protocol in background thread."""
        try:
            self.protocols_performer.perform_protocol(protocol_path)
            
            if self.protocols_performer.fresco_xyz.should_stop():
                self.after(0, lambda: self.log("[STOPPED] Protocol stopped by user", "info"))
                self.after(0, lambda: self.status_label.config(text="Stopped by user", fg="orange"))
            else:
                self.after(0, lambda: self.log("[SUCCESS] Protocol completed successfully!", "success"))
                self.after(0, lambda: self.status_label.config(text="Completed successfully", fg="green"))
            
        except Exception as e:
            error_msg = f"[ERROR] {type(e).__name__}: {str(e)}"
            self.after(0, lambda: self.log(error_msg, "error"))
            self.after(0, lambda: self.status_label.config(text="Error occurred", fg="red"))
        finally:
            self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))

    def stop_protocol(self):
        """Request protocol to stop."""
        if messagebox.askyesno("Stop Protocol", "Stop the current protocol?\n\nThe protocol will stop at the next checkpoint."):
            self.protocols_performer.fresco_xyz.request_stop()
            self.log("[STOP REQUESTED] Protocol will stop at next checkpoint...", "info")
            self.status_label.config(text="Stop requested...", fg="orange")

    def refresh(self):
        """Refresh protocol list."""
        protocols = self.protocols_performer.available_protocols()
        self.protocols_combobox['values'] = protocols
        if protocols:
            self.protocols_combobox.current(0)
        self.log(f"Refreshed: {len(protocols)} protocols found", "info")
