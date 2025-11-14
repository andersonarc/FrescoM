import tkinter as tk
from tkinter import scrolledtext
import sys
from io import StringIO
import threading


class StdoutCapture:
    def __init__(self, callback):
        self.callback = callback
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
    def write(self, text):
        self.original_stdout.write(text)
        if text.strip():
            self.callback(text)
    
    def flush(self):
        self.original_stdout.flush()


class StdoutView:
    def __init__(self):
        self.width = 800
        self.height = 800
        self.text_buffer = []
        self.max_lines = 1000
        
    def add_text(self, text):
        self.text_buffer.append(text)
        if len(self.text_buffer) > self.max_lines:
            self.text_buffer.pop(0)
    
    def get_current_image(self):
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (self.width, self.height), color='black')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        y_offset = 10
        line_height = 15
        
        # Show last lines that fit
        visible_lines = (self.height - 20) // line_height
        start_idx = max(0, len(self.text_buffer) - visible_lines)
        
        for line in self.text_buffer[start_idx:]:
            if y_offset >= self.height - line_height:
                break
            draw.text((10, y_offset), line.strip()[:100], fill='white', font=font)
            y_offset += line_height
        
        return np.array(img)
    
    def should_update_frequently(self):
        return True
    
    def set_exposure(self, millis: int):
        pass
    
    def set_auto_exposure(self, auto: bool):
        pass
