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
        self.max_lines = 2000
        self.lock = threading.Lock()

    def add_text(self, text):
        import time
        timestamp = time.strftime("%H:%M:%S")
        with self.lock:
            for line in text.split('\n'):
                if line.strip():
                    self.text_buffer.append((timestamp, line))
            if len(self.text_buffer) > self.max_lines:
                self.text_buffer = self.text_buffer[-self.max_lines:]

    def get_current_image(self):
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new('RGB', (self.width, self.height), color='#1e1e1e')
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 11)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 9)
        except:
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()

        y_offset = 10
        line_height = 14
        max_chars_per_line = 100  # Characters before wrapping

        with self.lock:
            visible_lines = (self.height - 20) // line_height
            start_idx = max(0, len(self.text_buffer) - visible_lines)
            buffer_copy = list(self.text_buffer[start_idx:])

        for timestamp, line in buffer_copy:
            if y_offset >= self.height - line_height:
                break

            color = '#d4d4d4'
            if 'ERROR' in line.upper() or 'FAIL' in line.upper():
                color = '#f48771'
            elif 'WARNING' in line.upper() or 'WARN' in line.upper():
                color = '#dcdcaa'
            elif 'SUCCESS' in line.upper() or 'OK' in line.upper():
                color = '#4ec9b0'
            elif 'INFO' in line.upper():
                color = '#9cdcfe'

            # Wrap long lines
            text = line.strip()
            wrapped_lines = []
            while len(text) > max_chars_per_line:
                wrapped_lines.append(text[:max_chars_per_line])
                text = text[max_chars_per_line:]
            if text:
                wrapped_lines.append(text)

            # Draw timestamp on first line only
            draw.text((10, y_offset), timestamp, fill='#6a9955', font=font_small)

            # Draw wrapped lines
            for i, wrapped_line in enumerate(wrapped_lines):
                if y_offset >= self.height - line_height:
                    break
                x_offset = 70 if i == 0 else 10  # Indent continuation lines
                draw.text((x_offset, y_offset), wrapped_line, fill=color, font=font)
                y_offset += line_height

        return np.array(img)
    
    def should_update_frequently(self):
        return True
    
    def set_exposure(self, millis: int):
        pass
    
    def set_auto_exposure(self, auto: bool):
        pass
