import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import socket
import threading
import cv2
import pyaudio
import struct
import time
import os
import numpy as np
from PIL import Image, ImageTk
import mss  # For screen capture
import uuid # Import UUID library
import base64 # For embedded icon
from datetime import datetime # (!!!) NEW: For feedback timestamp

# --- CONFIGURATION ---
# SERVER_IP = "172.16.208.18"  # !!! REMOVED: This will now be entered by the user
VIDEO_PORT = 9999
AUDIO_PORT = 9998
CHAT_PORT = 9997
FILE_PORT = 9996        # (!!!) This is now the FILE *CONTROL* port
FILE_DATA_PORT = 9993   # (!!!) NEW: This is for UPLOAD/DOWNLOAD
SCREEN_PORT = 9995
FEEDBACK_PORT = 9994 # (!!!) NEW: For feedback
BUFFER_SIZE = 65536 * 2 # Keep increased buffer

# Audio settings
CHUNK = 2048
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 22050

# --- Chat Settings ---
CHAT_MESSAGE_LIMIT = 256 # (!!!) NEW: Chat limit
FEEDBACK_MESSAGE_LIMIT = 512 # (!!!) NEW: Feedback limit

# --- Dynamic Grid Settings ---
MAX_GRID_COLS = 6
STREAM_TIMEOUT_SECONDS = 3.5 # Timeout before showing "Off" icon if no packets arrive
# (!!!) MODIFIED: Set width to 30% of 1200px
RIGHT_PANEL_WIDTH = 360 # Fallback width for right-side thumbnails
KEEPALIVE_INTERVAL = 1.0 # (!!!) MODIFIED: Was 2.5, now 1.0 for faster updates

# --- Simple Screen Share Settings ---
SCREEN_SHARE_QUALITY = 30
SCREEN_SHARE_WIDTH = 800
SCREEN_SHARE_FPS_DELAY = 0.2

# --- Base64 Encoded Camera-Off Icon (White on Black BG for visibility here) ---
CAM_OFF_ICON_B64 = "R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs="
# (!!!) NEW: Base64 Encoded Back Arrow Icon (White on Dark)
BACK_ARROW_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH6AoPFCUvP8Pz+AAAAjpJREFUWMPtlr1rFEEQhc9PFyKIFgooWIiFYCFYCP4SiIWFIlgoNjaClQsRLEQsiIWFYKPY2AhWYqNILEQsRApLpVgplkAEI0S8Ds/b7N3dnd2x8AcHZvYW5n3zzWw7AxzH+E9zLFXwVcAqcAacBc4CK/ATeE+vhCtwG/huMv8X+BewAswB3XAY2AAmgTHgCFgCprQdeB0YAuYFnNwCngCLwG/gV8AasARsByYDn4AXQDvwX2B74DeB3A/8A74CTwMf9HYJpHDNfA+csA6MAlPDd+CXwGfC74sZYBH4C1m1A9gP/AWeVt8Fnga+BfZeAJbC96M+2zTXfAc8A2ZcBWZeAeeAs8B2qP8AnA/8M/Ci2W0A3j8B7LnwEw8BW+BfYHst6A/ATwM/Ai/6vM1nw1/gM+A/YNsP/AnMuQqsAe8Bw+q0/wBwYJ7ZARgHvgF/AdstABs/Ac/6vLF9ge8Gfs/gJmB1yXwE/gOmTQP+xQGfNdqcAUwz2wPzvgMmwHZrwG/gW+BZ4G8kQo8CHwFfATvQuwK+A5clYJb4DPgRkKQAi8DBdCQBd8cMssAnw/q0CzwIfL9OaDvwRAnADXAemA/8BmwM+22AWWPMXoMvAs8Ct0sBK8sAvgMe/S9gDfgWGFVqA/8BXwGnQwa83kE7gBfD/sFfQ7uAc8AXYP/o3B5wN/CDP+h9gWcBn77Wqj/xHPCbT5BfAQsw3kH7B3wLzO6t9wQ8BI4+B/YFfATs3Bf6GfAB+A/4A/himk0+B34BfL4B/wYgD8/0E/Av23x+AAAAAElFTkSuQmCC"


class CollabClient:
    def __init__(self, root):
        self.root = root
        self.root.title("CIDER") # (!!!) RENAMED
        self.root.geometry("1200x800")
        self.root.minsize(800, 600) # (!!!) NEW: Set minimum size

        self.client_uuid = str(uuid.uuid4())
        print(f"DEBUG: My Client UUID: {self.client_uuid}")

        # --- State Variables ---
        self.username = "Guest"
        self.server_ip = "127.0.0.1" # Default IP
        self.is_connected = False
        self.video_sending = False
        self.audio_sending = False
        self.screen_sharing = False
        self.side_panel_visible = False
        self.current_side_view = 'none'

        # --- Sockets ---
        self.chat_socket = None
        self.file_socket = None
        self.feedback_socket = None # (!!!) NEW: Feedback socket
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.screen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # --- Media ---
        self.p_audio = pyaudio.PyAudio()
        self.sending_audio_stream = None
        self.receiving_audio_stream = None
        self.video_capture = None

        # --- Participant Grid Management (Refactored for separate streams) ---
        self.participant_widgets = {}
        self.image_references = {}
        self.last_active_stream = {}
        self.last_packet_time = {}
        self._removing_widgets = set() # Stores widget_key
        
        # (!!!) NEW: Debounce timer for screen share popups
        self.last_screen_stop_time = {}

        # --- User/Presence Management ---
        self.uuid_to_username = {}
        self.server_presence_set = set() # Authoritative list of UUIDs from server

        # --- Load Icons ---
        try:
            cam_off_data = base64.b64decode(CAM_OFF_ICON_B64)
            self.camera_off_icon = tk.PhotoImage(data=cam_off_data, master=self.root)
            # (!!!) NEW: Load back arrow icon
            back_arrow_data = base64.b64decode(BACK_ARROW_ICON_B64)
            self.back_arrow_icon = tk.PhotoImage(data=back_arrow_data, master=self.root)
            print("Icons loaded successfully.")
        except Exception as e:
            print(f"Error loading icons: {e}")
            self.camera_off_icon = None
            self.back_arrow_icon = None
        except Exception as e:
            print(f"Error loading icons: {e}")
            self.camera_off_icon = None
            self.back_arrow_icon = None

        # (!!!) --- ADD THIS DEBUG LINE --- (!!!)
        print(f"DEBUG: Back arrow icon object is: {self.back_arrow_icon}")

        # --- UI ---

        # --- UI ---
        # (!!!) MODIFIED: Define colors first
        self.define_colors()
        self.build_styles()
        
        # (!!!) NEW: Build the login screen first
        self.build_login_screen() 
        
        # (!!!) NEW: Create Feedback Page (hidden)
        self.build_feedback_page()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_stream_timeouts() # Start timeout checker

    # (!!!) NEW FUNCTION for colors
    def define_colors(self):
        # (!!!) NEW LIGHT THEME PALETTE (Shifted by user)
        self.BG_PRIMARY = "#E6D8C3"         # Light beige (was #F5F5F0)
        self.BG_SECONDARY = "#C2A68C"       # Muted brown/tan (was #E6D8C3)
        self.BG_SHADOW = "#a88a6d"          # Darker tan (was #C2A68C)
        
        # (!!!) Derived dark text for readability
        self.FG_TEXT = "#3D2F2F"            # Dark brown (for text)
        self.FG_TEXT_SECONDARY = "#5D866C"   # Muted green (for secondary text)
        self.BORDER_COLOR = "#C2A68C"       # Muted brown/tan
        
        self.ACCENT_PRIMARY = "#5D866C"     # Muted green
        self.ACCENT_PRIMARY_ACTIVE = "#4a6b56" # Darker green
        self.ACCENT_PRIMARY_FG = "#FFFFFF"  # White
        
        # Remap 'Red' and 'Green' to new theme
        self.ACCENT_RED = "#a88a6d"         # Darker tan (for 'Off' state)
        self.ACCENT_RED_ACTIVE = "#8e7156"    # Even darker tan (derived)
        self.ACCENT_GREEN = "#5D866C"       # Muted green (for 'On' state)
        self.ACCENT_GREEN_ACTIVE = "#4a6b56"  # Darker green
        
        self.FG_CIDER = "#5D866C"           # Muted green (for Login Title)
        self.BG_LOGIN_ENTRY = "#FFFFFF"     # White
        self.FG_LOGIN_ENTRY = "#3D2F2F"     # Dark brown (for text)
        # (!!!) END PALETTE UPDATE (!!!)


    # --- build_styles ---
    def build_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # (!!!) MODIFIED: Apply dark theme universally
        self.style.configure(".", background=self.BG_PRIMARY, foreground=self.FG_TEXT, font=('Segoe UI', 10))
        self.style.configure("TFrame", background=self.BG_PRIMARY)
        self.style.configure("TLabel", background=self.BG_PRIMARY, foreground=self.FG_TEXT)
        
        # Standard Button (e.g., Send, Upload, Close)
        self.style.configure("TButton", background=self.BG_SECONDARY, foreground=self.FG_TEXT, font=('Segoe UI', 10, 'bold'), borderwidth=0, padding=10, relief='flat')
        self.style.map("TButton", background=[('active', self.BORDER_COLOR)])
        
        # --- Control Bar Buttons ---
        self.style.configure("Danger.TButton", background=self.ACCENT_RED, foreground=self.ACCENT_PRIMARY_FG, font=('Segoe UI', 10, 'bold'), padding=10, relief='flat')
        self.style.map("Danger.TButton", background=[('active', self.ACCENT_RED_ACTIVE)])
        
        self.style.configure("Success.TButton", background=self.ACCENT_GREEN, foreground=self.ACCENT_PRIMARY_FG, font=('Segoe UI', 10, 'bold'), padding=10, relief='flat')
        self.style.map("Success.TButton", background=[('active', self.ACCENT_GREEN_ACTIVE)])

        # Toggle Buttons (Chat, Files)
        self.style.configure("Toggle.TButton", background=self.BG_SECONDARY, foreground=self.FG_TEXT, font=('Segoe UI', 10, 'bold'), padding=10, relief='flat')
        self.style.map("Toggle.TButton", background=[('active', self.BORDER_COLOR)])
        
        # (!!!) NEW: Feedback Button Style
        self.style.configure("Feedback.TButton", background=self.BG_SECONDARY, foreground=self.FG_TEXT, font=('Segoe UI', 10, 'bold'), padding=10, relief='flat')
        self.style.map("Feedback.TButton", background=[('active', self.BORDER_COLOR)])
        
        # (!!!) NEW: Feedback Back Button Style (using tk.Button for image)
        self.style.configure("FeedbackBack.TButton", 
            background=self.BG_PRIMARY, 
            foreground=self.FG_TEXT, 
            font=('Segoe UI', 14, 'bold'), 
            borderwidth=0, 
            relief='flat',
            compound='left',
            padding=(10, 5)
        )
        self.style.map("FeedbackBack.TButton", background=[('active', self.BG_SECONDARY)])
        
        # Chat Entry Box
        self.style.configure("TEntry", fieldbackground=self.BG_SECONDARY, foreground=self.FG_TEXT, insertcolor=self.FG_TEXT, borderwidth=1, relief='solid')
        self.style.map("TEntry", bordercolor=[('focus', self.ACCENT_PRIMARY), ('', self.BORDER_COLOR)])
        
        # (!!!) NEW: Small Send Button Style
        self.style.configure("Small.TButton", background=self.BG_SECONDARY, foreground=self.FG_TEXT, font=('Segoe UI', 9, 'bold'), borderwidth=0, padding=(10, 5), relief='flat')
        self.style.map("Small.TButton", background=[('active', self.BORDER_COLOR)])
        
        # Scrollbars
        self.style.configure("Vertical.TScrollbar", background=self.BG_SECONDARY, troughcolor=self.BG_PRIMARY, arrowcolor=self.FG_TEXT)
        self.style.configure("Horizontal.TScrollbar", background=self.BG_SECONDARY, troughcolor=self.BG_PRIMARY, arrowcolor=self.FG_TEXT)
        
        # Video/Thumbnail BG
        self.style.configure("Dark.TFrame", background="#000000")
        
        # Status Bar
        self.style.configure("Status.TFrame", background=self.BG_SECONDARY)
        self.style.configure("Status.TLabel", background=self.BG_SECONDARY, foreground=self.FG_TEXT_SECONDARY, font=('Segoe UI', 9))
        
        # (!!!) NEW: Character Count Labels
        self.style.configure("CharCount.TLabel", background=self.BG_PRIMARY, foreground=self.FG_TEXT_SECONDARY, font=('Segoe UI', 8))
        self.style.configure("FeedbackPage.TFrame", background=self.BG_PRIMARY)
        self.style.configure("FeedbackHeader.TFrame", background=self.BG_PRIMARY)
        self.style.configure("FeedbackTitle.TLabel", background=self.BG_PRIMARY, foreground=self.FG_TEXT, font=('Segoe UI', 14, 'bold'))
        self.style.configure("FeedbackPrompt.TLabel", background=self.BG_PRIMARY, foreground=self.FG_TEXT, font=('Segoe UI', 12))


    # (!!!) NEW FUNCTION: build_login_screen
    def build_login_screen(self):
        # (!!!) MODIFIED: Use new dark colors
        self.root.configure(bg=self.BG_PRIMARY)
        
        # This frame centers the login box
        self.login_container = tk.Frame(self.root, bg=self.BG_PRIMARY)
        self.login_container.place(relx=0.5, rely=0.5, anchor='center')

        # (!!!) NEW: Shadow frame
        shadow_frame = tk.Frame(self.login_container, bg=self.BG_SHADOW)
        shadow_frame.pack(padx=20, pady=20)

        # The actual login box (using tk.Frame for better styling)
        login_frame = tk.Frame(shadow_frame, bg=self.BG_SECONDARY)
        login_frame.pack(padx=2, pady=2) # This creates the 2px "shadow"
        
        # Inner frame for padding
        inner_frame = tk.Frame(login_frame, bg=self.BG_SECONDARY)
        inner_frame.pack(padx=30, pady=25)

        tk.Label(inner_frame, text="Welcome To", bg=self.BG_SECONDARY, fg=self.FG_TEXT, font=('Segoe UI', 14)).pack(pady=(0, 5))
        # (!!!) MODIFIED: Increased font size from 32 to 40
        tk.Label(inner_frame, text="CIDER", bg=self.BG_SECONDARY, fg=self.FG_CIDER, font=('Segoe UI', 40, 'bold')).pack(pady=(0, 20))

        # --- Entries Frame ---
        entries_frame = tk.Frame(inner_frame, bg=self.BG_SECONDARY)
        entries_frame.pack(fill='x')
        
        tk.Label(entries_frame, text="Username:", bg=self.BG_SECONDARY, fg=self.FG_TEXT, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', padx=5, pady=8)
        self.username_entry = tk.Entry(entries_frame, width=30, font=('Segoe UI', 12), bg=self.BG_LOGIN_ENTRY, fg=self.FG_LOGIN_ENTRY, borderwidth=0, relief="flat", insertbackground=self.FG_LOGIN_ENTRY)
        self.username_entry.grid(row=0, column=1, sticky='ew', padx=5, pady=8)
        self.username_entry.insert(0, f"User{np.random.randint(100, 999)}")
        
        tk.Label(entries_frame, text="IP Address:", bg=self.BG_SECONDARY, fg=self.FG_TEXT, font=('Segoe UI', 10)).grid(row=1, column=0, sticky='w', padx=5, pady=8)
        self.ip_entry = tk.Entry(entries_frame, width=30, font=('Segoe UI', 12), bg=self.BG_LOGIN_ENTRY, fg=self.FG_LOGIN_ENTRY, borderwidth=0, relief="flat", insertbackground=self.FG_LOGIN_ENTRY)
        self.ip_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=8)
        self.ip_entry.insert(0, self.server_ip) # Pre-fill with default

        entries_frame.grid_columnconfigure(1, weight=1)
        
        # (!!!) MODIFIED: Use tk.Button for style
        self.connect_btn = tk.Button(
            inner_frame, 
            text="CONNECT", 
            font=('Segoe UI', 12, 'bold'), 
            bg=self.ACCENT_PRIMARY, 
            fg=self.ACCENT_PRIMARY_FG, 
            borderwidth=0, 
            relief="flat", 
            activebackground=self.ACCENT_PRIMARY_ACTIVE, 
            activeforeground=self.ACCENT_PRIMARY_FG, 
            command=self.connect_to_server,
            pady=8
        )
        self.connect_btn.pack(pady=(20, 0), fill='x')


    # (!!!) NEW FUNCTION: build_status_bar
    def build_status_bar(self):
        # This frame holds all main app widgets (status, main content, controls)
        self.main_app_frame = ttk.Frame(self.root, style="TFrame")
        self.main_app_frame.pack(fill='both', expand=True) # Pack, don't place
        
        self.main_app_frame.grid_rowconfigure(0, weight=0)    # Status bar
        self.main_app_frame.grid_rowconfigure(1, weight=1)    # Main content
        self.main_app_frame.grid_rowconfigure(2, weight=0)    # Control bar
        self.main_app_frame.grid_columnconfigure(0, weight=1)

        status_frame = ttk.Frame(self.main_app_frame, style="Status.TFrame", padding=(10, 5))
        status_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 0))
        
        status_text = f"Hi, {self.username}! You are connected to {self.server_ip}"
        ttk.Label(status_frame, text=status_text, style="Status.TLabel").pack(side='left')

    # --- build_main_layout (Uses .grid) ---
    def build_main_layout(self):
        self.main_content_frame = ttk.Frame(self.main_app_frame, style="TFrame")
        # (!!!) MODIFIED: Grids to row=1, below the status bar
        self.main_content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 0))

        # Configure the grid *inside* main_content_frame
        self.main_content_frame.grid_columnconfigure(0, weight=1) # Video area expands
        self.main_content_frame.grid_columnconfigure(1, weight=0) # Side panel area (initially 0 width)
        self.main_content_frame.grid_rowconfigure(0, weight=1)

        # Video grid container
        self.video_grid_container = ttk.Frame(self.main_content_frame, style="TFrame")
        self.video_grid_container.grid(row=0, column=0, sticky="nsew")

        # Side panel (initially created, but not placed by 'grid')
        # (!!!) MODIFIED: Set consistent width for chat/file panel
        self.side_panel = ttk.Frame(self.main_content_frame, width=360, style="TFrame")
        self.side_panel.grid_propagate(False) # Don't shrink

    # --- build_control_bar (Uses .grid) ---
    def build_control_bar(self):
        control_bar_frame = ttk.Frame(self.main_app_frame, padding=15, style="TFrame")
        # (!!!) MODIFIED: Grids to row=2, below the main content
        control_bar_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=15)
        
        # (!!!) NEW: Left frame for feedback button
        left_frame = ttk.Frame(control_bar_frame, style="TFrame")
        left_frame.place(relx=0.0, rely=0.5, anchor='w', x=20)
        self.feedback_btn = ttk.Button(left_frame, text="Feedback", style="Feedback.TButton", command=self.show_feedback_page)
        self.feedback_btn.pack(side='left')

        center_frame = ttk.Frame(control_bar_frame, style="TFrame")
        center_frame.pack(side='top')
        self.audio_start_btn = ttk.Button(center_frame, text="🎤 Mic On", style="Danger.TButton", command=self.toggle_audio_send)
        self.audio_start_btn.pack(side='left', padx=10)
        self.video_start_btn = ttk.Button(center_frame, text="📷 Cam On", style="Danger.TButton", command=self.toggle_video_send)
        self.video_start_btn.pack(side='left', padx=10)
        self.screen_share_btn = ttk.Button(center_frame, text="🖥️ Present", style="Danger.TButton", command=self.toggle_screen_share)
        self.screen_share_btn.pack(side='left', padx=10)
        self.hangup_btn = ttk.Button(center_frame, text="📞 Hang Up", style="Danger.TButton", command=self.on_closing)
        self.hangup_btn.pack(side='left', padx=10)

        right_frame = ttk.Frame(control_bar_frame, style="TFrame")
        right_frame.place(relx=1.0, rely=0.5, anchor='e', x=-20)
        
        # (!!!) NEW: Participants Button
        self.participants_toggle_btn = ttk.Button(right_frame, text="👥 Participants", style="Toggle.TButton", command=lambda: self.toggle_side_panel('participants'))
        self.participants_toggle_btn.pack(side='left', padx=5)
        
        self.chat_toggle_btn = ttk.Button(right_frame, text="💬 Chat", style="Toggle.TButton", command=lambda: self.toggle_side_panel('chat'))
        self.chat_toggle_btn.pack(side='left', padx=5)
        self.file_toggle_btn = ttk.Button(right_frame, text="📁 Files", style="Toggle.TButton", command=lambda: self.toggle_side_panel('files'))
        self.file_toggle_btn.pack(side='left', padx=5)

        self.set_controls_state('disabled') # Will be enabled on successful connection
    
    # (!!!) --- NEW: FEEDBACK PAGE --- (!!!)
    def build_feedback_page(self):
        # This frame covers the *entire* root window
        self.feedback_page_frame = ttk.Frame(self.root, style="FeedbackPage.TFrame")
        # Don't pack or grid yet, will be .place()'d on top
        
        # --- Header ---
        feedback_header = ttk.Frame(self.feedback_page_frame, style="FeedbackHeader.TFrame", padding=(10, 5))
        feedback_header.pack(side='top', fill='x')
        
        # Use tk.Button for the image
        self.feedback_back_btn = tk.Button(
            feedback_header,
            text="Back", 
            font=('Segoe UI', 14, 'bold'),
            bg=self.BG_SECONDARY,                # (!!!) MODIFIED: Use theme variable
            fg=self.FG_TEXT,                   # (!!!) MODIFIED: Use theme variable
            activebackground=self.BG_SHADOW,     # (!!!) MODIFIED: Use theme variable
            activeforeground=self.FG_TEXT,       # (!!!) MODIFIED: Use theme variable
            borderwidth=0,
            relief='flat',
            padx=10,
            pady=5,
            command=self.hide_feedback_page
        )
        self.feedback_back_btn.pack(side='left', padx=(10, 5)) # (!!!) MODIFIED: Added right padding

        # (!!!) NEW: Add Feedback title label next to the button
        feedback_title_label = ttk.Label(
            feedback_header,
            text="Feedback",
            style="FeedbackTitle.TLabel" # Use the style defined in build_styles
        )
        feedback_title_label.pack(side='left', pady=5)


        # --- Content Area (centered) ---
        feedback_content = ttk.Frame(self.feedback_page_frame, style="FeedbackPage.TFrame")
        feedback_content.pack(side='top', fill='both', expand=True)

        center_frame = ttk.Frame(feedback_content, style="FeedbackPage.TFrame")
        center_frame.place(relx=0.5, rely=0.4, anchor='center', relwidth=0.6) # 60% width, centered

        prompt_label = ttk.Label(
            center_frame, 
            text="POST YOUR SUGGESTION OR REPORT YOUR PROBLEM", 
            style="FeedbackPrompt.TLabel",
            anchor='center'
        )
        prompt_label.pack(side='top', fill='x', pady=(0, 20))

        # Use tk.Text for multi-line, scrollable input
        self.feedback_text_box = tk.Text(
            center_frame, 
            height=10, 
            wrap=tk.WORD,
            font=('Segoe UI', 11),
            bg=self.BG_SECONDARY, # (!!!) Updated Color
            fg=self.FG_TEXT, # (!!!) Updated Color
            insertbackground=self.FG_TEXT, # (!!!) Updated Color
            borderwidth=1,
            relief='solid',
            highlightcolor=self.ACCENT_PRIMARY, # (!!!) Updated Color
            highlightbackground=self.BORDER_COLOR, # (!!!) Updated Color
            highlightthickness=1,
            padx=10,
            pady=10
        )
        self.feedback_text_box.pack(side='top', fill='x', expand=True, pady=(0, 5))
        self.feedback_text_box.bind("<KeyRelease>", self.update_feedback_count)

        self.feedback_char_count_label = ttk.Label(
            center_frame, 
            text=f"0/{FEEDBACK_MESSAGE_LIMIT}", 
            style="CharCount.TLabel",
            anchor='e'
        )
        self.feedback_char_count_label.pack(side='top', fill='x', padx=5)
        
        self.feedback_submit_btn = tk.Button(
            center_frame, 
            text="SUBMIT", 
            font=('Segoe UI', 12, 'bold'), 
            bg=self.ACCENT_PRIMARY, # (!!!) Updated Color
            fg=self.ACCENT_PRIMARY_FG, # (!!!) Updated Color
            borderwidth=0, 
            relief="flat", 
            activebackground=self.ACCENT_PRIMARY_ACTIVE, # (!!!) Updated Color
            activeforeground=self.ACCENT_PRIMARY_FG, # (!!!) Updated Color
            command=self.submit_feedback,
            pady=8
        )
        self.feedback_submit_btn.pack(side='top', fill='x', pady=(20, 0))

    def show_feedback_page(self):
        if self.feedback_page_frame.winfo_exists():
            self.feedback_page_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.main_app_frame.pack_forget() # Hide main app

    def hide_feedback_page(self):
        if self.feedback_page_frame.winfo_exists():
            self.feedback_page_frame.place_forget()
            self.main_app_frame.pack(fill='both', expand=True) # Show main app

    def update_feedback_count(self, event=None):
        content = self.feedback_text_box.get("1.0", "end-1c") # Get all text except trailing newline
        count = len(content)
        if count > FEEDBACK_MESSAGE_LIMIT:
            content = content[:FEEDBACK_MESSAGE_LIMIT]
            self.feedback_text_box.delete("1.0", "end")
            self.feedback_text_box.insert("1.0", content)
            count = FEEDBACK_MESSAGE_LIMIT
        
        self.feedback_char_count_label.config(text=f"{count}/{FEEDBACK_MESSAGE_LIMIT}")

    def submit_feedback(self):
        feedback_msg = self.feedback_text_box.get("1.0", "end-1c").strip()
        if not feedback_msg:
            messagebox.showwarning("Empty Feedback", "Please enter your feedback before submitting.", parent=self.feedback_page_frame)
            return
            
        if not self.is_connected or not self.feedback_socket:
            messagebox.showerror("Connection Error", "Not connected to the feedback server. Please try again.", parent=self.feedback_page_frame)
            return

        try:
            # Format: __FEEDBACK__||UUID||USERNAME||MESSAGE
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full_report = f"__FEEDBACK__||{self.client_uuid}||{self.username}||{timestamp}||{feedback_msg}"
            
            # Send the feedback in a separate thread
            threading.Thread(target=self.send_feedback_thread, args=(full_report.encode('utf-8'),), daemon=True).start()
            
            messagebox.showinfo("Feedback Sent", "Thank you! Your feedback has been submitted.", parent=self.feedback_page_frame)
            self.feedback_text_box.delete("1.0", "end")
            self.update_feedback_count()
            self.hide_feedback_page()

        except Exception as e:
            print(f"[Feedback Submit Error] {e}")
            messagebox.showerror("Error", f"Could not send feedback: {e}", parent=self.feedback_page_frame)
            
    def send_feedback_thread(self, encoded_report):
        """Sends feedback on a new temporary socket to avoid blocking."""
        temp_sock = None
        try:
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_sock.settimeout(5)
            temp_sock.connect((self.server_ip, FEEDBACK_PORT))
            
            # Send length-prefixed packet
            report_len = struct.pack('I', len(encoded_report))
            temp_sock.sendall(report_len + encoded_report)
            print("[Feedback] Feedback sent successfully.")
        except Exception as e:
            print(f"[Send Feedback Error] {e}")
            # Silently fail for now, but log it
        finally:
            if temp_sock:
                try: temp_sock.close()
                except: pass
    
    # (!!!) --- END FEEDBACK PAGE --- (!!!)

    # --- build_side_panel_content ---
    def build_side_panel_content(self):
        header_frame = ttk.Frame(self.side_panel, padding=(10, 10))
        header_frame.pack(side='top', fill='x')
        self.side_panel_title = ttk.Label(header_frame, text="Chat", font=('Segoe UI', 14, 'bold'))
        self.side_panel_title.pack(side='left')
        close_btn = ttk.Button(header_frame, text="✕", command=self.hide_side_panel)
        close_btn.pack(side='right')
        self.side_content_frame = ttk.Frame(self.side_panel, padding=(10, 0, 10, 10))
        self.side_content_frame.pack(side='top', fill='both', expand=True)
        
        self.chat_widget_frame = ttk.Frame(self.side_content_frame)
        self.build_chat_ui(self.chat_widget_frame)
        self.file_widget_frame = ttk.Frame(self.side_content_frame)
        self.build_file_ui(self.file_widget_frame)
        self.chat_widget_frame = ttk.Frame(self.side_content_frame)
        self.build_chat_ui(self.chat_widget_frame)
        self.file_widget_frame = ttk.Frame(self.side_content_frame)
        self.build_file_ui(self.file_widget_frame)

        # (!!!) NEW: Participants UI
        self.participants_widget_frame = ttk.Frame(self.side_content_frame)
        self.build_participants_ui(self.participants_widget_frame)

    # --- set_controls_state ---
    def set_controls_state(self, state):
        buttons = [
            getattr(self, name, None) for name in 
            ['audio_start_btn', 'video_start_btn', 'screen_share_btn',
             'hangup_btn', 'chat_toggle_btn', 'file_toggle_btn', 'feedback_btn',
             'participants_toggle_btn'] # (!!!) NEW
        ]
        for btn in buttons:
             if btn and btn.winfo_exists():
                 try: 
                     # ttk buttons use 'state' config
                     if isinstance(btn, ttk.Button):
                         btn.config(state=state)
                     # tk buttons (like feedback back) use 'state' config
                     elif isinstance(btn, tk.Button):
                         btn.config(state=state)
                 except tk.TclError: pass
                 
        # Handle chat/file/feedback widgets
        widgets = [
            getattr(self, name, None) for name in
            ['msg_entry', 'send_btn', 'upload_btn', 
             'feedback_text_box', 'feedback_submit_btn']
        ]
        for widget in widgets:
            if widget and widget.winfo_exists():
                try: 
                    widget_state = 'normal' if state == 'normal' else 'disabled'
                    # tk.Text uses 'state'
                    if isinstance(widget, tk.Text):
                        widget.config(state=widget_state)
                    # ttk.Entry and ttk.Button use 'state'
                    else:
                        widget.config(state=widget_state)
                except (tk.TclError, AttributeError): pass

    # (!!!) --- NEW: NOTIFICATION FUNCTION --- (!!!)
    def _set_notification_state(self, view_name, new_state):
        """
        Sets or clears the notification state for a side panel button.
        new_state = True (Set notification), False (Clear notification)
        """
        try:
            if view_name == 'chat':
                if new_state: # Trying to SET notification
                    # Don't set if it's already set or if the panel is open
                    if self.chat_notification or self.current_side_view == 'chat':
                        return
                    self.chat_notification = True
                    if hasattr(self, 'chat_toggle_btn') and self.chat_toggle_btn.winfo_exists():
                        self.chat_toggle_btn.config(text="💬 Chat*")
                
                else: # Trying to CLEAR notification
                    if not self.chat_notification:
                        return
                    self.chat_notification = False
                    if hasattr(self, 'chat_toggle_btn') and self.chat_toggle_btn.winfo_exists():
                        self.chat_toggle_btn.config(text="💬 Chat")
            
            elif view_name == 'files':
                if new_state: # Trying to SET notification
                    # Don't set if it's already set or if the panel is open
                    if self.file_notification or self.current_side_view == 'files':
                        return
                    self.file_notification = True
                    if hasattr(self, 'file_toggle_btn') and self.file_toggle_btn.winfo_exists():
                        self.file_toggle_btn.config(text="📁 Files*")
                
                else: # Trying to CLEAR notification
                    if not self.file_notification:
                        return
                    self.file_notification = False
                    if hasattr(self, 'file_toggle_btn') and self.file_toggle_btn.winfo_exists():
                        self.file_toggle_btn.config(text="📁 Files")
        
        except Exception as e:
            print(f"[Notification Error] {e}")

    # --- toggle_side_panel ---
    def toggle_side_panel(self, view_to_show):
        if self.side_panel_visible and self.current_side_view == view_to_show:
            self.hide_side_panel()
        else:
            self.show_side_panel_view(view_to_show)

    # --- hide_side_panel ---
    def hide_side_panel(self):
        if hasattr(self, 'side_panel') and self.side_panel.winfo_exists():
            self.side_panel.grid_forget()
        if hasattr(self, 'main_content_frame') and self.main_content_frame.winfo_exists():
            self.main_content_frame.grid_columnconfigure(1, weight=0, minsize=0)
        self.side_panel_visible = False
        self.current_side_view = 'none'
        
        # (!!!) NEW: Notification state trackers
        self.chat_notification = False
        self.file_notification = False

    # --- show_side_panel_view ---
    def show_side_panel_view(self, view_name):
        if not hasattr(self, 'main_content_frame') or not self.main_content_frame.winfo_exists():
            return
            
        self.main_content_frame.grid_columnconfigure(1, weight=0, minsize=360)

        if not self.side_panel_visible:
            if hasattr(self, 'side_panel') and self.side_panel.winfo_exists():
                self.side_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
            self.side_panel_visible = True

        if hasattr(self, 'chat_widget_frame') and self.chat_widget_frame.winfo_exists(): self.chat_widget_frame.pack_forget()
        if hasattr(self, 'file_widget_frame') and self.file_widget_frame.winfo_exists(): self.file_widget_frame.pack_forget()
        # (!!!) NEW: Forget participants frame
        if hasattr(self, 'participants_widget_frame') and self.participants_widget_frame.winfo_exists(): self.participants_widget_frame.pack_forget()


        if view_name == 'chat':
            if hasattr(self, 'side_panel_title') and self.side_panel_title.winfo_exists(): self.side_panel_title.config(text="Chat")
            if hasattr(self, 'chat_widget_frame') and self.chat_widget_frame.winfo_exists(): self.chat_widget_frame.pack(fill='both', expand=True)
            self.current_side_view = 'chat'
        elif view_name == 'files':
            if hasattr(self, 'side_panel_title') and self.side_panel_title.winfo_exists(): self.side_panel_title.config(text="File Sharing")
            if hasattr(self, 'file_widget_frame') and self.file_widget_frame.winfo_exists(): self.file_widget_frame.pack(fill='both', expand=True)
            self.current_side_view = 'files'
        # (!!!) NEW: Show participants frame
        elif view_name == 'participants':
            if hasattr(self, 'side_panel_title') and self.side_panel_title.winfo_exists(): self.side_panel_title.config(text="Participants")
            if hasattr(self, 'participants_widget_frame') and self.participants_widget_frame.winfo_exists(): self.participants_widget_frame.pack(fill='both', expand=True)
            self.current_side_view = 'participants'# (!!!) NEW: Clear notification when opening a panel
        if view_name == 'chat':
            self._set_notification_state('chat', False)
        elif view_name == 'files':
            self._set_notification_state('files', False)
        

    # --- connect_to_server ---
    def connect_to_server(self):
        # (!!!) MODIFIED: Get username and IP from entries
        self.username = self.username_entry.get().strip()
        self.server_ip = self.ip_entry.get().strip()
        
        if not self.username:
            messagebox.showerror("Error", "Please enter a username.")
            return
        if not self.server_ip:
            messagebox.showerror("Error", "Please enter an IP Address.")
            return
        
        self.uuid_to_username[self.client_uuid] = self.username
        self.connect_btn.config(text="Connecting...", state='disabled')
        self.root.update_idletasks()

        try:
            print(f"Connecting to chat server at {self.server_ip}...")
            self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.chat_socket.settimeout(5)
            self.chat_socket.connect((self.server_ip, CHAT_PORT))
            self.chat_socket.settimeout(None)
            print("Chat connected.")

            register_msg = f"__REGISTER_USER__||{self.client_uuid}||{self.username}"
            self.chat_socket.sendall(register_msg.encode('utf-8'))
            print(f"Sent user registration: {register_msg}")

            print(f"Connecting to file server at {self.server_ip}...")
            self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.file_socket.settimeout(5)
            self.file_socket.connect((self.server_ip, FILE_PORT))
            self.file_socket.settimeout(None)
            print("File connected.")
            
            # (!!!) NEW: Connect to feedback socket (just to check)
            print(f"Connecting to feedback server at {self.server_ip}...")
            self.feedback_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.feedback_socket.settimeout(5)
            self.feedback_socket.connect((self.server_ip, FEEDBACK_PORT))
            # We close this immediately, it's just a test.
            # Real feedback uses temporary sockets.
            self.feedback_socket.close()
            self.feedback_socket = True # Set to True to indicate success
            print("Feedback server checked.")


            self.video_socket.bind(("0.0.0.0", 0))
            self.audio_socket.bind(("0.0.0.0", 0))
            self.screen_socket.bind(("0.0.0.0", 0))

            register_header = f"REGISTER||{self.client_uuid}||{self.username}".encode('utf-8')
            self.video_socket.sendto(register_header, (self.server_ip, VIDEO_PORT))
            self.audio_socket.sendto(register_header, (self.server_ip, AUDIO_PORT))
            self.screen_socket.sendto(register_header, (self.server_ip, SCREEN_PORT))
            print("UDP registration packets sent with UUID and Username.")

            self.is_connected = True
            
            # (!!!) NEW: Destroy login UI and build main app UI
            self.login_container.destroy()
            
            # (!!!) NEW: Build the main UI components
            self.build_status_bar() # This now creates self.main_app_frame
            self.build_main_layout()
            self.build_side_panel_content()
            self.build_control_bar()
            
            self.set_controls_state('normal') # Enable controls

            # (!!!) MODIFICATION: Just register data, don't create UI
            self.add_participant_widget('local', 'video')
            self.add_participant_widget('local', 'screen')

            threading.Thread(target=self.receive_chat, daemon=True).start()
            threading.Thread(target=self.receive_file, daemon=True).start()
            threading.Thread(target=self.receive_video, daemon=True).start()
            threading.Thread(target=self.receive_audio, daemon=True).start()
            threading.Thread(target=self.receive_screen, daemon=True).start()
            threading.Thread(target=self.send_keepalive, daemon=True).start()
            print("Receiver threads started.")


        except socket.timeout:
             messagebox.showerror("Connection Failed", f"Connection to {self.server_ip} timed out.\nCheck IP and server status.")
             print("Connection timeout.")
             self.is_connected = False
             self.connect_btn.config(text="Connect", state='normal')
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Could not connect to {self.server_ip}:\n{e}")
            print(f"Connection error: {e}")
            self.is_connected = False
            if hasattr(self, 'connect_btn'): # Check if login screen still exists
                self.connect_btn.config(text="Connect", state='normal')
            for sock in [self.chat_socket, self.file_socket, self.feedback_socket]:
                if sock and isinstance(sock, socket.socket):
                    try: sock.close()
                    except: pass
            self.feedback_socket = None

    # --- send_keepalive ---
    def send_keepalive(self):
        keepalive_packet = f"KEEPALIVE||{self.client_uuid}||{self.username}".encode('utf-8')
        while self.is_connected:
            try:
                self.video_socket.sendto(keepalive_packet, (self.server_ip, VIDEO_PORT))
                self.audio_socket.sendto(keepalive_packet, (self.server_ip, AUDIO_PORT))
                self.screen_socket.sendto(keepalive_packet, (self.server_ip, SCREEN_PORT))
            except Exception as e:
                if self.is_connected: print(f"[KeepAlive Error] {e}")
            time.sleep(KEEPALIVE_INTERVAL)
        print("--- Keep-alive thread finished. ---")


    # ----------------- VIDEO -----------------

    def reset_video_label(self, widget_key, is_screen=False):
        widget_info = self.participant_widgets.get(widget_key)
        # (!!!) MODIFICATION: Check if widgets exist before resetting
        if widget_info and widget_info['label'] and widget_info['name_label']:
            label = widget_info['label']
            name_label = widget_info['name_label']
            participant_uuid = widget_info['uuid']
            print(f"--- [RESET] Attempting reset for {widget_key} ---")
            try:
                if label.winfo_exists():
                    self.image_references.pop(widget_key, None)
                    display_name = "You" if participant_uuid == 'local' else self.uuid_to_username.get(participant_uuid, participant_uuid[:8]+"...")
                    off_text = f"{display_name}\n(Screen Off)" if is_screen else f"{display_name}\n(Camera Off)"

                    # (!!!) THIS IS THE FIX: Set a dynamic wraplength
                    label_wraplength = RIGHT_PANEL_WIDTH - 20 # Give it some padding
                    label.config(image='', text=off_text, bg="black", fg="white", compound=tk.CENTER, wraplength=label_wraplength)
                    label.image = None # Ensure no image reference
                    
                    if name_label.winfo_exists():
                        name_label.config(text=display_name)
                    print(f"--- [RESET] Successfully reset label config for {widget_key} ---")
            except Exception as e:
                 print(f"[Reset Label Error] Error during reset config for {widget_key}: {e}")

    # --- toggle_video_send ---
    def toggle_video_send(self):
        if self.video_sending:
            self.video_sending = False
            self.video_start_btn.config(text="📷 Cam On", style="Danger.TButton")
            if self.video_capture:
                try: self.video_capture.release()
                except Exception as e: print(f"[Video Toggle Error] Release failed: {e}")
                self.video_capture = None
            
            try:
                print("--- [VIDEO] Sending VIDEOCAM_OFF command. ---")
                off_packet = f"VIDEOCAM_OFF||{self.client_uuid}||".encode('utf-8')
                for _ in range(3):
                    self.video_socket.sendto(off_packet, (self.server_ip, VIDEO_PORT))
                    time.sleep(0.01)
            except Exception as e: print(f"[Video Toggle Error] Failed to send OFF command: {e}")

            self.reset_video_label('local_video')
            if self.last_active_stream.get('local') == 'video':
                self.last_active_stream['local'] = 'none'
            self.rebuild_video_grid() # Rebuild to show "Cam Off" status
            print("--- [VIDEO] Local video stopped. ---")
        else:
            self.video_sending = True
            self.video_start_btn.config(text="📸 Cam Off", style="Success.TButton")
            try:
                print("--- [VIDEO] Attempting to open webcam...")
                self.video_capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not self.video_capture.isOpened():
                    print("--- [VIDEO] DSHOW failed, trying default backend...")
                    if self.video_capture: self.video_capture.release()
                    self.video_capture = cv2.VideoCapture(0)
                    if not self.video_capture.isOpened():
                         raise cv2.error("Could not open webcam with DSHOW or default backend.")

                print("--- [VIDEO] Webcam opened successfully. Starting send thread.")
                threading.Thread(target=self.send_video, daemon=True).start()
            except Exception as e:
                messagebox.showerror("Webcam Error", f"Could not open webcam.\nMake sure it's not used by another app.\nError: {e}")
                print(f"[Webcam Error] {e}")
                self.video_sending = False
                self.video_start_btn.config(text="📷 Cam On", style="Danger.TButton")
                if self.video_capture: self.video_capture.release()
                self.video_capture = None

    # --- send_video ---
    def send_video(self):
        print("--- [VIDEO] Send thread started.")
        frame_count = 0
        try:
            while self.video_sending and self.video_capture and self.video_capture.isOpened():
                ret, frame = self.video_capture.read()
                if not ret:
                    print("[Send Video Warning] Failed to read frame.")
                    time.sleep(0.1); continue

                frame_preview = cv2.resize(frame, (640, 480))
                ret_encode, buffer = cv2.imencode('.jpg', frame_preview, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret_encode: continue

                buffer_bytes = buffer.tobytes()
                buffer_len = len(buffer_bytes)

                if 0 < buffer_len <= 65500 :
                     header = f"VIDEO||{self.client_uuid}||".encode('utf-8')
                     self.video_socket.sendto(header + buffer_bytes, (self.server_ip, VIDEO_PORT))
                     frame_count += 1
                elif buffer_len > 65500:
                     print(f"[Send Video Warning] Frame {frame_count} too large ({buffer_len}), skipping.")

                time.sleep(0.03)
        except Exception as e:
            print(f"[Send Video Error] In loop (frame {frame_count}): {e}")
            self.video_sending = False
        finally:
            print("--- [VIDEO] Send thread finished.")
            
            was_unexpected_exit = self.video_sending
            
            if was_unexpected_exit:
                print("--- [VIDEO] Loop exited unexpectedly. Forcing UI reset. ---")
                self.video_sending = False 

            self.root.after(0, lambda: [
                self.video_start_btn.config(text="📷 Cam On", style="Danger.TButton") if hasattr(self, 'video_start_btn') and self.video_start_btn.winfo_exists() else None,
                self.reset_video_label('local_video'),
                self.last_active_stream.update({'local': 'none'}) if self.last_active_stream.get('local') == 'video' else None,
                self.rebuild_video_grid()
            ])

    # ----------------- SCREEN SHARING -----------------

    # --- toggle_screen_share ---
    def toggle_screen_share(self):
        if self.screen_sharing:
            self.screen_sharing = False
            self.screen_share_btn.config(text="🖥️ Present", style="Danger.TButton")

            try:
                print("--- [SCREEN] Sending SCREEN_OFF command. ---")
                off_packet = f"SCREEN_OFF||{self.client_uuid}||".encode('utf-8')
                for _ in range(3):
                    self.screen_socket.sendto(off_packet, (self.server_ip, SCREEN_PORT))
                    time.sleep(0.01)
            except Exception as e: print(f"[Screen Toggle Error] Failed to send OFF command: {e}")

            self.reset_video_label('local_screen', is_screen=True)
            if self.last_active_stream.get('local') == 'screen':
                self.last_active_stream['local'] = 'video' if self.video_sending else 'none'
            # (!!!) MODIFIED: Remove system message
            # self.root.after(0, self.display_message, f"[System] You have stopped sharing your screen.")
            self.root.after(10, self.rebuild_video_grid)
            print("--- [SCREEN] Local screen share stopped. ---")

        else:
            presenter_uuid = None
            for p_uuid, stream_type in self.last_active_stream.items():
                 if stream_type == 'screen' and p_uuid != 'local':
                      presenter_uuid = p_uuid
                      break
            if presenter_uuid:
                presenter_name = self.uuid_to_username.get(presenter_uuid, presenter_uuid[:8]+"...")
                messagebox.showwarning("Screen Share", f"{presenter_name} is already presenting.")
                return

            self.screen_sharing = True
            self.screen_share_btn.config(text="🛑 Stop Presenting", style="Success.TButton")
            self.last_active_stream['local'] = 'screen'
            # (!!!) MODIFIED: Remove system message
            # self.root.after(0, self.display_message, f"[System] You have started sharing your screen.")
            self.rebuild_video_grid()
            threading.Thread(target=self.send_screen, daemon=True).start()

    # --- send_screen ---
    def send_screen(self):
        print("--- [SCREEN] Send thread started.")
        jpeg_quality = SCREEN_SHARE_QUALITY
        frame_delay = SCREEN_SHARE_FPS_DELAY
        target_width = SCREEN_SHARE_WIDTH
        frame_count = 0
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                while self.screen_sharing:
                    try:
                        img = sct.grab(monitor)
                        pil_image = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                        w_ratio = target_width / pil_image.width if pil_image.width > 0 else 1
                        target_height = max(1, int(pil_image.height * w_ratio))
                        frame_preview = pil_image.resize((target_width, target_height), Image.LANCZOS)

                        frame_preview_np = np.array(frame_preview)
                        frame_bgr = cv2.cvtColor(frame_preview_np, cv2.COLOR_RGB2BGR)
                        ret_encode, buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                        if not ret_encode: continue

                        buffer_bytes = buffer.tobytes()
                        buffer_len = len(buffer_bytes)

                        if 0 < buffer_len <= 65500:
                             header = f"SCREEN||{self.client_uuid}||".encode('utf-8')
                             self.screen_socket.sendto(header + buffer_bytes, (self.server_ip, SCREEN_PORT))
                             frame_count += 1
                        elif buffer_len > 65500:
                             print(f"[Send Screen Warning] Frame {frame_count} too large ({buffer_len}), skipping.")

                        time.sleep(frame_delay)
                    except mss.exception.ScreenShotError as e:
                        print(f"[Send Screen Error] mss failed: {e}")
                        self.screen_sharing = False
                    except Exception as e:
                        print(f"[Send Screen Error] Inner loop error (frame {frame_count}): {e}")
                        self.screen_sharing = False
        except Exception as e:
             print(f"[Send Screen Error] Failed to initialize mss: {e}")
             self.screen_sharing = False
        finally:
            print("--- [SCREEN] Send thread finished.")
            
            was_unexpected_exit = self.screen_sharing

            if was_unexpected_exit:
                print("--- [SCREEN] Loop exited unexpectedly. Forcing UI reset. ---")
                self.screen_sharing = False 

            self.root.after(0, lambda: [
                self.screen_share_btn.config(text="🖥️ Present", style="Danger.TButton") if hasattr(self, 'screen_share_btn') and self.screen_share_btn.winfo_exists() else None,
                self.reset_video_label('local_screen', is_screen=True),
                self.last_active_stream.update({'local': ('video' if self.video_sending else 'none')}) if self.last_active_stream.get('local') == 'screen' else None,
                self.rebuild_video_grid()
            ])


    # ----------------- MEDIA RECEIVERS & TIMEOUT -----------------

    # --- process_received_frame ---
    def process_received_frame(self, data):
        """Processes VIDEO or SCREEN frames: TYPE||UUID||DATA"""
        try:
            delimiter = b'||'
            if not data or delimiter not in data or data.count(delimiter) < 2:
                return # Malformed

            header_part, uuid_part_bytes, frame_data = data.split(delimiter, 2)
            packet_type = header_part.decode('utf-8', 'ignore') # VIDEO or SCREEN
            sender_uuid = uuid_part_bytes.decode('utf-8', 'ignore')

            participant_uuid = 'local' if sender_uuid == self.client_uuid else sender_uuid
            stream_type = 'screen' if packet_type == 'SCREEN' else 'video'
            widget_key = f"{participant_uuid}_{stream_type}"

            if participant_uuid == 'local':
                if stream_type == "video" and not self.video_sending: return # Discard
                if stream_type == "screen" and not self.screen_sharing: return # Discard

            self.last_packet_time[widget_key] = time.time()

            # (!!!) --- FIX for Race Condition --- (!!!)
            # Check for the widget *before* any logic.
            widget_info = self.participant_widgets.get(widget_key)
            if not widget_info:
                if participant_uuid == 'local':
                    print(f"[Process Frame Error] Got 'local' packet for non-existent widget {widget_key}. Ignoring.")
                    return # This shouldn't happen, but good to guard.

                # This is a stream from a participant that joined before the
                # PRESENCE packet was processed. We MUST create the widget data now.
                print(f"--- [Process Frame] Race condition detected. Creating widget data for {widget_key} ---")
                self.add_participant_widget(participant_uuid, stream_type)
                
                # We must also add the _other_ widget type, just in case
                other_stream_type = 'video' if stream_type == 'screen' else 'screen'
                other_widget_key = f"{participant_uuid}_{other_stream_type}"
                if other_widget_key not in self.participant_widgets:
                     # This will schedule a rebuild
                     self.add_participant_widget(participant_uuid, other_stream_type)
                
                # Now, get the widget_info again
                widget_info = self.participant_widgets.get(widget_key)
                if not widget_info:
                    print(f"[Process Frame Error] Failed to create widget data for {widget_key} on the fly. Bailing.")
                    return
            # (!!!) --- END FIX --- (!!!)


            old_primary_stream = self.last_active_stream.get(participant_uuid, 'none')
            if stream_type == 'screen':
                new_primary_stream = 'screen'
            elif old_primary_stream != 'screen':
                new_primary_stream = 'video'
            else:
                new_primary_stream = old_primary_stream

            needs_rebuild = False
            
            if self.last_active_stream.get(participant_uuid) != new_primary_stream:
                 self.last_active_stream[participant_uuid] = new_primary_stream
                 needs_rebuild = True
                 print(f"--- Primary Stream update for {participant_uuid}: {old_primary_stream} -> {new_primary_stream} ---")

                 if participant_uuid != 'local' and new_primary_stream == 'screen':
                     display_name = self.uuid_to_username.get(sender_uuid, sender_uuid[:8]+"...")
                     
                     # (!!!) FIX: Check debounce timer before showing "started" popup
                     last_stop_time = self.last_screen_stop_time.get(participant_uuid, 0)
                     if (time.time() - last_stop_time) > 2.0: # Only show if stopped > 2s ago
                         self.root.after(0, messagebox.showinfo, "Screen Share", f"Hey, {display_name} has started sharing their screen!")
            
            if stream_type == 'video':
                current_presenter = None
                for p_uuid, s_type in self.last_active_stream.items():
                    if s_type == 'screen':
                        current_presenter = p_uuid
                        break
                
                if current_presenter is None: # Grid mode
                    if old_primary_stream == 'none': # Was 'none', now 'video'
                        needs_rebuild = True
                        print(f"--- Triggering grid rebuild (Grid mode, new video: {participant_uuid}) ---")

            
            # We already checked for widget_info at the top.
            # Now we just check if the UI 'frame' has been built by rebuild_video_grid.
            if not widget_info['frame']:
                # If the UI frame doesn't exist, a rebuild is needed (if not already pending)
                if not needs_rebuild:
                    print(f"--- Triggering grid rebuild (Widget UI {widget_key} missing) ---")
                    # We don't need to call add_participant_widget here,
                    # because we did it at the top. We just need to trigger a rebuild.
                    self.root.after(100, self.rebuild_video_grid)
                return # Return and wait for the rebuild to create the UI frame.
                
            frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), 1)
            if frame is None:
                print(f"[Process Frame Warning] Failed {packet_type} decode from {sender_uuid[:8]}")
                return

            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            self.root.after(0, self.update_participant_label, widget_key, pil_image)

            if needs_rebuild:
                print(f"--- Triggering grid rebuild (Primary stream change: {participant_uuid}) ---")
                self.root.after(100, self.rebuild_video_grid)

        except Exception as e:
             if self.is_connected: print(f"[Process Frame Error] {e} | Data: {data[:60]}...")

    # --- receive_video ---
    def receive_video(self):
        print("--- [VIDEO] Receive thread started.")
        while self.is_connected:
            try:
                data, server_addr = self.video_socket.recvfrom(BUFFER_SIZE)

                if data.startswith(b'PRESENCE||'):
                    try:
                        parts = data.decode('utf-8', 'ignore').split('||')
                        participant_pairs = parts[1:]
                        new_presence_set = set()
                        new_names = {}
                        for pair in participant_pairs:
                            try: # Expect UUID:Username
                                uuid_str, username = pair.split(':', 1)
                                if uuid_str:
                                    new_presence_set.add(uuid_str)
                                    new_names[uuid_str] = username
                            except ValueError: continue

                        self.server_presence_set = new_presence_set
                        self.uuid_to_username = new_names
                        if self.client_uuid not in self.uuid_to_username:
                             self.uuid_to_username[self.client_uuid] = self.username
                        
                        self.root.after(0, self.sync_participants_from_presence)
                        # (!!!) ADD THIS LINE:
                        self.root.after(0, self.update_participants_list_ui) 
                    except Exception as e: print(f"[Presence Error] {e} | Data: {data[:100]}")
                    continue

                elif data.startswith(b'STREAM_OFF||'):
                    try:
                        parts = data.decode('utf-8', 'ignore').split('||')
                        if len(parts) >= 3:
                            uuid_str, stream_type_str = parts[1], parts[2].lower()
                            if stream_type_str not in ('video', 'screen'): continue

                            participant_uuid = 'local' if uuid_str == self.client_uuid else uuid_str
                            widget_key = f"{participant_uuid}_{stream_type_str}"
                            
                            print(f"--- [STREAM_OFF] Received for {widget_key} ---")
                            self.root.after(0, self.reset_video_label, widget_key, (stream_type_str == 'screen'))

                            if self.last_active_stream.get(participant_uuid) == stream_type_str:
                                video_key = f"{participant_uuid}_video"
                                new_primary = 'video' if (stream_type_str == 'screen' and self._is_stream_active(video_key)) else 'none'
                                
                                if self.last_active_stream.get(participant_uuid) != new_primary:
                                    print(f"--- [STREAM_OFF] Updating primary state for {participant_uuid} to '{new_primary}' ---")
                                    self.last_active_stream[participant_uuid] = new_primary
                                    
                                    # (!!!) FIX: Set stop time for debounce
                                    if stream_type_str == 'screen':
                                        self.last_screen_stop_time[participant_uuid] = time.time()
                                        
                                    self.root.after(100, self.rebuild_video_grid)

                                    # (!!!) FIX: Popup moved INSIDE state change check
                                    if participant_uuid != 'local' and stream_type_str == 'screen':
                                        display_name = self.uuid_to_username.get(uuid_str, uuid_str[:8]+"...")
                                        self.root.after(0, messagebox.showinfo, "Screen Share", f"{display_name} stopped sharing.")
                            
                    except Exception as e: print(f"[Stream OFF Error] {e} | Data: {data[:60]}")
                    continue

                else:
                    self.process_received_frame(data)

            except socket.timeout: continue
            except OSError as e:
                if self.is_connected: print(f"[Socket Video Error] {e}"); break
            except Exception as e:
                if self.is_connected: print(f"[Receive Video Error] {e}")
        print("--- [VIDEO] Receive thread finished.")

    # --- receive_screen ---
    def receive_screen(self):
        print("--- [SCREEN] Receive thread started.")
        while self.is_connected:
            try:
                data, server_addr = self.screen_socket.recvfrom(BUFFER_SIZE)

                if data.startswith(b'STREAM_OFF||'):
                    try:
                        parts = data.decode('utf-8', 'ignore').split('||')
                        if len(parts) >= 3:
                            uuid_str, stream_type_str = parts[1], parts[2].lower()
                            if stream_type_str not in ('video', 'screen'): continue
                            participant_uuid = 'local' if uuid_str == self.client_uuid else uuid_str
                            widget_key = f"{participant_uuid}_{stream_type_str}"
                            
                            print(f"--- [STREAM_OFF] Received for {widget_key} ---")
                            self.root.after(0, self.reset_video_label, widget_key, (stream_type_str == 'screen'))

                            if self.last_active_stream.get(participant_uuid) == stream_type_str:
                                video_key = f"{participant_uuid}_video"
                                new_primary = 'video' if (stream_type_str == 'screen' and self._is_stream_active(video_key)) else 'none'
                                
                                if self.last_active_stream.get(participant_uuid) != new_primary:
                                    print(f"--- [STREAM_OFF] Updating primary state for {participant_uuid} to '{new_primary}' ---")
                                    self.last_active_stream[participant_uuid] = new_primary
                                    
                                    # (!!!) FIX: Set stop time for debounce
                                    if stream_type_str == 'screen':
                                        self.last_screen_stop_time[participant_uuid] = time.time()
                                        
                                    self.root.after(100, self.rebuild_video_grid)
                            
                                    # (!!!) FIX: Popup moved INSIDE state change check
                                    if participant_uuid != 'local' and stream_type_str == 'screen':
                                        display_name = self.uuid_to_username.get(uuid_str, uuid_str[:8]+"...")
                                        self.root.after(0, messagebox.showinfo, "Screen Share", f"{display_name} stopped sharing.")
                            
                    except Exception as e: print(f"[Stream OFF Error] {e} | Data: {data[:60]}")
                    continue

                else:
                    self.process_received_frame(data)

            except socket.timeout: continue
            except OSError as e:
                 if self.is_connected: print(f"[Socket Screen Error] {e}"); break
            except Exception as e:
                if self.is_connected: print(f"[Receive Screen Error] {e}")
        print("--- [SCREEN] Receive thread finished.")

    # --- _is_stream_active (Helper) ---
    def _is_stream_active(self, widget_key):
        if widget_key == 'local_video':
            return self.video_sending
        if widget_key == 'local_screen':
            return self.screen_sharing
        
        last_time = self.last_packet_time.get(widget_key)
        if last_time is None: return False
        return (time.time() - last_time) <= STREAM_TIMEOUT_SECONDS

    # --- check_stream_timeouts ---
    def check_stream_timeouts(self):
        if not self.is_connected:
            self.root.after(1000, self.check_stream_timeouts) # Keep checking to restart later
            return

        now = time.time()
        needs_rebuild = False
        
        current_widget_keys = list(self.participant_widgets.keys())

        for widget_key in current_widget_keys:
             widget_info_safe = self.participant_widgets.get(widget_key)
             if not widget_info_safe:
                 continue

             if widget_info_safe['uuid'] == 'local':
                 continue
                 
             last_time = self.last_packet_time.get(widget_key)
             
             if last_time is None: 
                 continue 
             
             if now - last_time > STREAM_TIMEOUT_SECONDS:
                print(f"--- [TIMEOUT] Stream timeout detected for {widget_key} ---")
                
                widget_info = self.participant_widgets.get(widget_key)
                if not widget_info:
                    self.last_packet_time.pop(widget_key, None)
                    continue
                
                participant_uuid = widget_info['uuid']
                stream_type = widget_info['stream_type']
                
                self.reset_video_label(widget_key, (stream_type == 'screen'))
                self.last_packet_time.pop(widget_key, None)
                
                if self.last_active_stream.get(participant_uuid) == stream_type:
                    if stream_type == 'screen':
                        video_key = f"{participant_uuid}_video"
                        new_primary = 'video' if self._is_stream_active(video_key) else 'none'
                        
                        # (!!!) FIX: Set debounce timer on timeout
                        self.last_screen_stop_time[participant_uuid] = time.time()
                    else:
                        new_primary = 'none'
                    
                    if self.last_active_stream.get(participant_uuid) != new_primary:
                         print(f"--- [TIMEOUT] Updating primary state for {participant_uuid} to '{new_primary}' ---")
                         self.last_active_stream[participant_uuid] = new_primary
                         needs_rebuild = True

        if self.is_connected and needs_rebuild:
             print("--- [TIMEOUT] Rebuilding grid due to primary stream timeout ---")
             self.root.after(100, self.rebuild_video_grid)

        if self.is_connected:
            self.root.after(1000, self.check_stream_timeouts)


    # ----------------- DYNAMIC GRID LOGIC -----------------

    # --- sync_participants_from_presence ---
    def sync_participants_from_presence(self):
        if not self.is_connected: return
        
        server_uuids = self.server_presence_set
        
        for participant_uuid in server_uuids:
            if participant_uuid == self.client_uuid: continue
            
            video_key = f"{participant_uuid}_video"
            screen_key = f"{participant_uuid}_screen"

            if video_key not in self.participant_widgets and video_key not in self._removing_widgets:
                print(f"--- [PRESENCE SYNC] Adding widget data {video_key} ---")
                self.add_participant_widget(participant_uuid, 'video')
            
            if screen_key not in self.participant_widgets and screen_key not in self._removing_widgets:
                print(f"--- [PRESENCE SYNC] Adding widget data {screen_key} ---")
                self.add_participant_widget(participant_uuid, 'screen')

        current_widget_uuids = set(info['uuid'] for info in self.participant_widgets.values())
        to_remove_uuids = current_widget_uuids - server_uuids - {'local'}
        
        for uuid_to_remove in to_remove_uuids:
            video_key = f"{uuid_to_remove}_video"
            screen_key = f"{uuid_to_remove}_screen"
            
            if video_key in self.participant_widgets:
                print(f"--- [PRESENCE SYNC] Removing widget data {video_key} ---")
                self.remove_participant_widget(video_key)
            if screen_key in self.participant_widgets:
                print(f"--- [PRESENCE SYNC] Removing widget data {screen_key} ---")
                self.remove_participant_widget(screen_key)

    # --- update_participant_label ---
    def update_participant_label(self, widget_key, pil_image):
        try:
            widget_info = self.participant_widgets.get(widget_key)
            # (!!!) MODIFICATION: Check if widgets have been created
            if not widget_info or not widget_info['frame'] or not widget_info['label']:
                return

            label = widget_info['label']
            frame_widget = widget_info['frame']
            participant_uuid = widget_info['uuid']

            if not self.root.winfo_exists() or not frame_widget.winfo_exists() or not label.winfo_exists():
                 return

            if participant_uuid == 'local' and widget_info['stream_type'] == 'video':
                pil_image = pil_image.transpose(Image.FLIP_LEFT_RIGHT)

            is_presenter_mode = any(s == 'screen' for s in self.last_active_stream.values())
            is_thumbnail = False
            if is_presenter_mode:
                presenter_uuid = None
                for p_uuid, stream_type in self.last_active_stream.items():
                    # (!!!) FIX: Check if stream is active
                    if stream_type == 'screen' and self._is_stream_active(f"{p_uuid}_screen"):
                        presenter_uuid = p_uuid
                        break
                
                if widget_key != f"{presenter_uuid}_screen":
                    is_thumbnail = True

            if is_thumbnail:
                # (!!!) MODIFIED: Read dynamic width
                frame_widget.update_idletasks()
                frame_width = frame_widget.winfo_width()
                frame_height = frame_widget.winfo_height()
                if frame_width < 10: frame_width = RIGHT_PANEL_WIDTH - 4 # Fallback
                if frame_height < 10: frame_height = int(frame_width * (3/4)) # Fallback
            else:
                frame_widget.update_idletasks()
                frame_width = frame_widget.winfo_width()
                frame_height = frame_widget.winfo_height()

                # (!!!) THIS IS THE FIX (!!!)
                if frame_width < 10 or frame_height < 10: 
                    print(f"[Update Label Debug] {widget_key} frame not ready ({frame_width}x{frame_height}). Skipping update.")
                    return # Skip this frame update, wait for next one

            img_w, img_h = pil_image.size
            if img_w <= 0 or img_h <= 0: return

            frame_aspect = frame_width / frame_height if frame_height > 0 else 1
            img_aspect = img_w / img_h if img_h > 0 else 1

            if img_aspect > frame_aspect:
                new_width = frame_width
                new_height = max(1, int(new_width / img_aspect))
            else:
                new_height = frame_height
                new_width = max(1, int(new_height * img_aspect))

            new_size = (new_width, new_height)
            resized_image = pil_image.resize(new_size, Image.LANCZOS)
            img_tk = ImageTk.PhotoImage(image=resized_image)

            if label.winfo_exists():
                self.image_references[widget_key] = img_tk
                label.config(image=img_tk, text="", bg="black", compound=tk.CENTER)
                label.image = img_tk

        except tk.TclError as e:
            if "invalid command name" not in str(e) and self.is_connected:
                print(f"[Update Label Error] TclError for {widget_key}: {e}")
        except Exception as e:
            if self.is_connected:
                print(f"[Update Label Error] Other for {widget_key}: {e}")

    # (!!!) NEW ARCHITECTURE: add_participant_widget just stores data
    def add_participant_widget(self, participant_uuid, stream_type):
        widget_key = f"{participant_uuid}_{stream_type}"
        if widget_key in self.participant_widgets or widget_key in self._removing_widgets:
            return
        print(f"Adding participant widget entry: {widget_key}")

        self.participant_widgets[widget_key] = {
            'frame': None, # Will be created by rebuild_video_grid
            'label': None, # Will be created by rebuild_video_grid
            'name_label': None, # Will be created by rebuild_video_grid
            'uuid': participant_uuid,
            'stream_type': stream_type
        }
        
        self.root.after(50, self.rebuild_video_grid)

    # (!!!) NEW ARCHITECTURE: remove_participant_widget just removes data
    def remove_participant_widget(self, widget_key):
        if widget_key in self._removing_widgets: return

        widget_info = self.participant_widgets.pop(widget_key, None) # Pop from main dict
        if widget_info:
            print(f"Scheduling removal for widget data: {widget_key}")
            self._removing_widgets.add(widget_key) # Keep track to avoid race conditions
            
            # Clear old data
            self.image_references.pop(widget_key, None)
            self.last_packet_time.pop(widget_key, None)
            
            participant_uuid = widget_info['uuid']
            stream_type = widget_info['stream_type']

            if self.last_active_stream.get(participant_uuid) == stream_type:
                if stream_type == 'screen':
                    video_key = f"{participant_uuid}_video"
                    new_primary = 'video' if self._is_stream_active(video_key) else 'none'
                else:
                    new_primary = 'none'
                
                if self.last_active_stream.get(participant_uuid) != new_primary:
                    print(f"--- [REMOVAL] Updating primary state for {participant_uuid} to '{new_primary}' ---")
                    self.last_active_stream[participant_uuid] = new_primary
            
            # Don't destroy UI here, rebuild_video_grid will handle it
            self.root.after(50, self._finalize_widget_removal, widget_key)
        else:
             print(f"Attempted to remove {widget_key}, widget info not found.")
             self._removing_widgets.discard(widget_key)


    def _finalize_widget_removal(self, widget_key):
        self._removing_widgets.discard(widget_key)
        print(f"Finalized removal for {widget_key}")
        
        if self.is_connected and self.root.winfo_exists() and self.video_grid_container.winfo_exists():
            self.rebuild_video_grid()

    # (!!!) NEW HELPER FUNCTION
    def _create_p_frame(self, parent_widget, widget_key):
        """Helper to create and store a participant frame."""
        widget_info = self.participant_widgets.get(widget_key)
        if not widget_info:
            print(f"[Create P Frame Error] No info for {widget_key}")
            return None

        participant_uuid = widget_info['uuid']
        stream_type = widget_info['stream_type']
        
        p_frame = ttk.Frame(parent_widget, borderwidth=1, relief="solid", style="TFrame")
        
        display_name = "You" if participant_uuid == 'local' else self.uuid_to_username.get(participant_uuid, participant_uuid[:8]+"...")
        
        off_text = f"{display_name}\n(Screen Off)" if stream_type == 'screen' else f"{display_name}\n(Camera Off)"
        
        # (!!!) THIS IS THE FIX: Set a wraplength based on the *panel* width
        # This prevents the label from requesting a width larger than the panel.
        label_wraplength = RIGHT_PANEL_WIDTH - 20 # Give it some padding
        
        p_label = tk.Label(p_frame, bg="black", text=off_text, fg="white", font=('Segoe UI', 9), compound=tk.CENTER, wraplength=label_wraplength)
        p_label.image = None
        p_label.pack(fill="both", expand=True)

        name_label = tk.Label(p_frame, text=display_name, bg="black", fg="white", font=('Segoe UI', 9, 'bold'), padx=4, pady=1)
        name_label.place(relx=0.0, rely=1.0, anchor='sw', x=2, y=-2)
        
        p_frame.pack_propagate(False)
        
        # Store the created widgets
        widget_info['frame'] = p_frame
        widget_info['label'] = p_label
        widget_info['name_label'] = name_label
        
        # Reset the label to its default "Off" state
        self.reset_video_label(widget_key, (stream_type == 'screen'))
        
        return p_frame

    # (!!!) NEW ARCHITECTURE: rebuild_video_grid creates all UI
    def rebuild_video_grid(self):
        """(MODIFIED) Re-calculates layout: Grid or Presenter + Right-Side Thumbnails."""
        try:
            if not self.is_connected or not self.root.winfo_exists() or not hasattr(self, 'video_grid_container') or not self.video_grid_container.winfo_exists():
                return
            print("--- Rebuilding video grid ---")

            # --- (!!!) NEW: Destroy all old frames managed by this grid ---
            for widget in list(self.video_grid_container.winfo_children()):
                if widget.winfo_exists():
                    widget.destroy() # Destroy old grid frames, thumbnail strips, etc.

            # --- (!!!) NEW: Clear widget references ---
            for info in self.participant_widgets.values():
                info['frame'] = None
                info['label'] = None
                info['name_label'] = None

            # --- (FIXED) Reset grid config (clear all weights) ---
            for i in range(self.video_grid_container.grid_size()[1] + 1): self.video_grid_container.grid_rowconfigure(i, weight=0, minsize=0)
            for i in range(self.video_grid_container.grid_size()[0] + 1): self.video_grid_container.grid_columnconfigure(i, weight=0, minsize=0)

            # --- Determine Presenter ---
            presenter_uuid = None
            for p_uuid, stream_type in self.last_active_stream.items():
                if stream_type == 'screen':
                    if self._is_stream_active(f"{p_uuid}_screen"):
                        presenter_uuid = p_uuid
                        break
            
            presenter_widget_key = f"{presenter_uuid}_screen" if presenter_uuid else None

            # --- Get ALL widgets that are not pending removal ---
            all_widgets_to_display = {
                key: info for key, info in self.participant_widgets.items()
                if key not in self._removing_widgets
            }
            
            # --- Apply Layout ---
            if presenter_widget_key and presenter_widget_key in all_widgets_to_display:
                # --- (FIXED) NEW PRESENTER MODE: Large screen share on left, thumbnails on right ---
                presenter_name = self.uuid_to_username.get(presenter_uuid, presenter_uuid[:8]+"...")
                print(f"Grid Mode: Presenter ({presenter_name}) - Right Thumbnails")

                # (!!!) MODIFIED: Set weight to 70/30 split
                self.video_grid_container.grid_columnconfigure(0, weight=70) # Main presenter column
                self.video_grid_container.grid_columnconfigure(1, weight=30) # Side strip column
                self.video_grid_container.grid_rowconfigure(0, weight=1) # Single row

                # (!!!) NEW: Create and Grid the presenter's *screen* frame
                presenter_frame = self._create_p_frame(self.video_grid_container, presenter_widget_key)
                if presenter_frame and presenter_frame.winfo_exists():
                    presenter_frame.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

                # --- (!!!) NEW: DYNAMIC THUMBNAIL LOGIC (!!!) ---
                right_thumbnail_strip = ttk.Frame(self.video_grid_container, style="Dark.TFrame")
                right_thumbnail_strip.grid(row=0, column=1, sticky="nsew", padx=(5,0), pady=0)
                
                # (!!!) MODIFIED: Get width/height dynamically
                right_thumbnail_strip.update_idletasks()
                available_height = right_thumbnail_strip.winfo_height()
                # (!!!) FIX: Read the width *after* update_idletasks
                thumb_width = right_thumbnail_strip.winfo_width() - 4 # -4 for padx=2
                
                if available_height <= 1: # Fallback if not rendered
                    available_height = self.video_grid_container.winfo_height()
                if thumb_width <= 10: # Fallback
                    thumb_width = RIGHT_PANEL_WIDTH - 4
                
                padding = 4 # pady=2 top and bottom

                # Get list of thumbnails to build
                thumbnail_keys = []
                all_participant_uuids = set(self.uuid_to_username.keys())
                all_participant_uuids.add('local')
                all_participant_uuids.discard(self.client_uuid) 
                sorted_uuids = sorted(list(all_participant_uuids), key=lambda x: (x != 'local', x))

                for p_uuid in sorted_uuids:
                    video_widget_key = f"{p_uuid}_video"
                    if video_widget_key in all_widgets_to_display:
                        thumbnail_keys.append(video_widget_key)
                
                thumb_count = len(thumbnail_keys)
                if thumb_count == 0:
                    print("  No thumbnails to display.")
                    # No return, just leave the panel black
                
                # --- (!!!) MODIFIED: Decide Layout: Expand or Scroll? ---
                if 0 < thumb_count <= 3:
                    # --- SCENARIO 1: 3 or fewer, expand them to fill ---
                    print(f"  Placing {thumb_count} thumbnails in 'Expand' mode.")
                    # No canvas/scrollbar needed, pack directly into the strip
                    for widget_key in thumbnail_keys:
                        p_frame = self._create_p_frame(right_thumbnail_strip, widget_key)
                        if p_frame and p_frame.winfo_exists():
                            # Pack with expand=True to fill the space
                            p_frame.pack(side="top", fill="both", expand=True, padx=2, pady=2)
                            if not self._is_stream_active(widget_key):
                                self.reset_video_label(widget_key, is_screen=False)
                
                elif thumb_count > 3:
                    # --- SCENARIO 2: More than 3, use scrollbar ---
                    print(f"  Placing {thumb_count} thumbnails in 'Scroll' mode.")
                    right_thumbnail_strip.grid_propagate(False) # Prevent strip from resizing
                    
                    # (!!!) NEW LOGIC: Calculate height as if there were 3
                    if available_height > 10: # Ensure available_height is valid
                        # Calculate height for 3 items, remove padding for each
                        ideal_thumb_height = (available_height / 3.0) - padding
                    else:
                        # (!!!) FIX: Calculate fallback height based on *calculated* thumb_width
                        ideal_thumb_height = int(thumb_width * (3/4)) # Fallback
                    
                    ideal_thumb_height = max(50, int(ideal_thumb_height)) # Ensure a minimum height

                    thumbnail_canvas = tk.Canvas(right_thumbnail_strip, bg="#000000", highlightthickness=0)
                    thumbnail_scrollbar = ttk.Scrollbar(right_thumbnail_strip, orient="vertical", command=thumbnail_canvas.yview, style="Vertical.TScrollbar")
                    thumbnail_scrollable_frame = ttk.Frame(thumbnail_canvas, style="Dark.TFrame")
                    
                    thumbnail_scrollable_frame.bind("<Configure>", lambda e, c=thumbnail_canvas: c.configure(scrollregion=c.bbox("all")) if c.winfo_exists() else None)
                    thumbnail_canvas_window = thumbnail_canvas.create_window((0, 0), window=thumbnail_scrollable_frame, anchor="nw")
                    
                    def configure_canvas_window(event, canvas=thumbnail_canvas, window=thumbnail_canvas_window):
                        if canvas.winfo_exists(): canvas.itemconfigure(window, width=event.width)
                    thumbnail_canvas.bind("<Configure>", configure_canvas_window)
                    
                    thumbnail_canvas.configure(yscrollcommand=thumbnail_scrollbar.set)
                    thumbnail_scrollbar.pack(side="right", fill="y")
                    thumbnail_canvas.pack(side="left", fill="both", expand=True)
                    
                    current_y = 0
                    for widget_key in thumbnail_keys:
                        p_frame = self._create_p_frame(thumbnail_scrollable_frame, widget_key)
                        if p_frame and p_frame.winfo_exists():
                            # (!!!) THIS IS THE FIX: No fill="x", no expand=True. Set width manually.
                            p_frame.pack(side="top", expand=False, padx=2, pady=2)
                            p_frame.config(width=thumb_width, height=ideal_thumb_height)
                            
                            if not self._is_stream_active(widget_key):
                                self.reset_video_label(widget_key, is_screen=False)
                            current_y += ideal_thumb_height + padding
                    
                    if thumbnail_scrollable_frame.winfo_exists():
                        thumbnail_scrollable_frame.config(height=max(1, current_y))
                    if thumbnail_canvas.winfo_exists():
                        self.root.after(5, lambda c=thumbnail_canvas: c.configure(scrollregion=c.bbox("all")) if c.winfo_exists() else None)
                # --- (!!!) END DYNAMIC THUMBNAIL LOGIC (!!!) ---

            else:
                # --- (FIXED) NORMAL GRID MODE ---
                print("Grid Mode: Normal")
                
                all_participant_uuids = set(self.uuid_to_username.keys())
                all_participant_uuids.add('local')
                all_participant_uuids.discard(self.client_uuid)

                widgets_to_grid = []
                for p_uuid in all_participant_uuids:
                    primary_stream = self.last_active_stream.get(p_uuid, 'none')
                    screen_widget_key = f"{p_uuid}_screen"
                    video_widget_key = f"{p_uuid}_video"

                    is_screen_active = self._is_stream_active(screen_widget_key)
                    is_video_active = self._is_stream_active(video_widget_key)

                    if primary_stream == 'screen' and is_screen_active and screen_widget_key in all_widgets_to_display:
                        widgets_to_grid.append(screen_widget_key)
                    elif (primary_stream == 'video' or not is_screen_active) and is_video_active and video_widget_key in all_widgets_to_display:
                        widgets_to_grid.append(video_widget_key)
                    elif video_widget_key in all_widgets_to_display:
                        widgets_to_grid.append(video_widget_key)
                    elif screen_widget_key in all_widgets_to_display:
                        widgets_to_grid.append(screen_widget_key)
                
                num_participants = len(widgets_to_grid)

                if num_participants == 0:
                    print("  No participants to display in grid.")
                    if 'local_video' in all_widgets_to_display:
                        # (!!!) NEW: Create local_video frame
                        p_frame = self._create_p_frame(self.video_grid_container, 'local_video')
                        self.video_grid_container.grid_rowconfigure(0, weight=1)
                        self.video_grid_container.grid_columnconfigure(0, weight=1)
                        if p_frame and p_frame.winfo_exists(): 
                            p_frame.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
                    return

                cols = min(MAX_GRID_COLS, num_participants)
                if num_participants == 1: cols = 1
                elif num_participants <= 4: cols = 2
                elif num_participants <= 6: cols = 3
                elif num_participants <= 9: cols = 3
                else: cols = 4
                rows = (num_participants + cols - 1) // cols

                for r in range(rows): self.video_grid_container.grid_rowconfigure(r, weight=1, minsize=150)
                for c in range(cols): self.video_grid_container.grid_columnconfigure(c, weight=1, minsize=200)

                for i, widget_key in enumerate(widgets_to_grid):
                     # (!!!) NEW: Create frame
                     p_frame = self._create_p_frame(self.video_grid_container, widget_key)
                     row, col = divmod(i, cols)
                     if p_frame and p_frame.winfo_exists():
                         p_frame.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
                         
                         if not self._is_stream_active(widget_key):
                             self.reset_video_label(widget_key, is_screen=(self.participant_widgets[widget_key]['stream_type'] == 'screen'))

        except Exception as e:
             if self.is_connected: print(f"[Rebuild Grid Error] {e}")


    # ----------------- AUDIO -----------------

    # --- toggle_audio_send ---
    def toggle_audio_send(self):
        if self.audio_sending:
            self.audio_sending = False
            self.audio_start_btn.config(text="🎤 Mic On", style="Danger.TButton") # Red = Off
            if self.sending_audio_stream:
                try:
                    if self.sending_audio_stream.is_active(): self.sending_audio_stream.stop_stream()
                    self.sending_audio_stream.close()
                except Exception as e: print(f"[Audio Toggle Error - Stop] {e}")
                self.sending_audio_stream = None
        else:
            self.audio_sending = True
            self.audio_start_btn.config(text="🔇 Mic Off", style="Success.TButton") # Green = On
            try:
                self.sending_audio_stream = self.p_audio.open(
                    format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK
                )
                threading.Thread(target=self.send_audio, daemon=True).start()
            except Exception as e:
                messagebox.showerror("Audio Error", f"Could not open microphone:\n{e}")
                self.audio_sending = False
                self.audio_start_btn.config(text="🎤 Mic On", style="Danger.TButton")

    # --- send_audio ---
    def send_audio(self):
        print("--- [AUDIO] Send thread started.")
        try:
            while self.audio_sending and self.sending_audio_stream:
                try:
                    data = self.sending_audio_stream.read(CHUNK, exception_on_overflow=False)
                    header = f"AUDIO||{self.client_uuid}||".encode('utf-8')
                    self.audio_socket.sendto(header + data, (self.server_ip, AUDIO_PORT))
                except IOError as e:
                     if self.audio_sending: print(f"[Send Audio IO Error] {e}")
                     self.audio_sending = False
                except Exception as e:
                    print(f"[Send Audio Error] {e}")
                    self.audio_sending = False
        finally:
            print("--- [AUDIO] Send thread finished.")
            self.root.after(0, lambda: self.audio_start_btn.config(text="🎤 Mic On", style="Danger.TButton") if hasattr(self, 'audio_start_btn') and self.audio_start_btn.winfo_exists() and not self.audio_sending else None)
            if self.sending_audio_stream:
                try:
                    if self.sending_audio_stream.is_active(): self.sending_audio_stream.stop_stream()
                    self.sending_audio_stream.close()
                except: pass
                self.sending_audio_stream = None

    # --- receive_audio ---
    def receive_audio(self):
        print("--- [AUDIO] Receive thread started.")
        try:
            self.receiving_audio_stream = self.p_audio.open(
                format=FORMAT, channels=CHANNELS, rate=RATE,
                output=True, frames_per_buffer=CHUNK
            )
        except Exception as e:
            print(f"[Receive Audio Error] Could not open output stream: {e}")
            return

        while self.is_connected:
            try:
                data, recv_addr = self.audio_socket.recvfrom(BUFFER_SIZE)
                if not data: continue

                delimiter = b'||'
                if delimiter not in data or data.count(delimiter) < 2: continue

                header_part, uuid_part_bytes, audio_data = data.split(delimiter, 2)
                packet_type = header_part.decode('utf-8', 'ignore')

                if packet_type != "AUDIO": continue

                sender_uuid = uuid_part_bytes.decode('utf-8', 'ignore')
                if sender_uuid == self.client_uuid: continue # Don't play own audio

                if audio_data and self.receiving_audio_stream:
                    try:
                        if not self.receiving_audio_stream.is_stopped():
                             self.receiving_audio_stream.write(audio_data)
                        else:
                             print("[Receive Audio Warning] Output stream was stopped. Reopening.")
                             try: self.receiving_audio_stream.close()
                             except: pass
                             self.receiving_audio_stream = self.p_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
                             self.receiving_audio_stream.write(audio_data)

                    except IOError as write_error:
                        print(f"[Receive Audio Write Error] {write_error}. Closing stream.")
                        try:
                            if self.receiving_audio_stream:
                                self.receiving_audio_stream.stop_stream()
                                self.receiving_audio_stream.close()
                        except: pass
                        self.receiving_audio_stream = None
                        self.root.after(1000, self._try_reopen_audio_output)

            except OSError as e:
                 if self.is_connected: print(f"[Receive Audio Socket Error] {e}"); break
            except Exception as e:
                if self.is_connected: print(f"[Receive Audio General Error] {e}")
                time.sleep(0.01)

        print("--- [AUDIO] Receive thread finished.")
        if self.receiving_audio_stream:
            try:
                if not self.receiving_audio_stream.is_stopped(): self.receiving_audio_stream.stop_stream()
                self.receiving_audio_stream.close()
            except Exception as e: print(f"[Audio Receive Cleanup Error] {e}")
            self.receiving_audio_stream = None

    # --- _try_reopen_audio_output ---
    def _try_reopen_audio_output(self):
        """Attempts to reopen the audio output stream if it closed unexpectedly."""
        if self.is_connected and not self.receiving_audio_stream:
            print("[Audio] Attempting to reopen output stream...")
            try:
                self.receiving_audio_stream = self.p_audio.open(
                    format=FORMAT, channels=CHANNELS, rate=RATE,
                    output=True, frames_per_buffer=CHUNK
                )
                print("[Audio] Output stream reopened successfully.")
            except Exception as e:
                print(f"[Audio Error] Failed to reopen output stream: {e}")
                if self.is_connected:
                    self.root.after(5000, self._try_reopen_audio_output)


    # ----------------- CHAT -----------------
    
    # (!!!) NEW: Validation function for chat limit
    def _validate_chat_input(self, text_content):
        return len(text_content) <= CHAT_MESSAGE_LIMIT

    # (!!!) NEW: Update character count
    def update_chat_count(self, event=None):
        content = self.msg_entry.get()
        count = len(content)
        # Enforce limit (though validation should prevent this)
        if count > CHAT_MESSAGE_LIMIT:
            content = content[:CHAT_MESSAGE_LIMIT]
            self.msg_entry.delete(CHAT_MESSAGE_LIMIT, tk.END)
            count = CHAT_MESSAGE_LIMIT
        
        self.chat_char_count_label.config(text=f"{count}/{CHAT_MESSAGE_LIMIT}")


    # --- build_chat_ui ---
    def build_chat_ui(self, parent_frame):
        # (!!!) FIX: Create all widgets first, then pack them in the correct order.
        
        # 1. Create the bottom container for the entry, button, and count
        msg_frame_container = ttk.Frame(parent_frame, style="TFrame")
        
        # 2. Create widgets for the bottom container
        validate_cmd = (self.root.register(self._validate_chat_input), '%P')
        self.msg_entry = ttk.Entry(msg_frame_container, validate='key', validatecommand=validate_cmd)
        
        self.msg_entry.bind("<KeyRelease>", self.update_chat_count)
        self.msg_entry.bind("<Return>", self.send_chat_event)
        
        # (!!!) NEW: Frame for the bottom bar (count + send)
        bottom_bar_frame = ttk.Frame(msg_frame_container, style="TFrame")

        self.chat_char_count_label = ttk.Label(
            bottom_bar_frame, 
            text=f"0/{CHAT_MESSAGE_LIMIT}", 
            style="CharCount.TLabel"
            # anchor='w' is default for pack(side='left')
        )
        
        # (!!!) MODIFIED: Use new 'Small.TButton' style
        self.send_btn = ttk.Button(bottom_bar_frame, text="Send", command=self.send_chat, style="Small.TButton")
        
        # 3. Create the main chat history box
        self.chat_box = scrolledtext.ScrolledText(
            parent_frame, bg=self.BG_SECONDARY, fg=self.FG_TEXT, state='disabled',
            wrap=tk.WORD, font=('Segoe UI', 10), padx=5, pady=5, borderwidth=0, relief="flat",
            insertbackground=self.FG_TEXT, 
            width=1 
        )
        
        self.chat_box.tag_configure("system", foreground=self.FG_TEXT_SECONDARY, font=('Segoe UI', 9, 'italic'))
        self.chat_box.tag_configure("username", foreground=self.ACCENT_PRIMARY, font=('Segoe UI', 10, 'bold'))
        self.chat_box.tag_configure("message", foreground=self.FG_TEXT, font=('Segoe UI', 10))
        
        
        # (!!!) 4. Pack them in the correct order (!!!)
        
        # Pack the bottom container FIRST, so it reserves its space at the bottom.
        msg_frame_container.pack(side='bottom', fill='x')
        
        # Pack the children inside the bottom container
        # (!!!) MODIFIED: Pack entry box on top
        self.msg_entry.pack(side='top', fill='x', padx=(0, 0), pady=(0, 3)) # Pack entry at the top, fill x
        bottom_bar_frame.pack(side='top', fill='x') # Pack bar below entry, fill x

        # Pack children inside the bottom bar
        self.chat_char_count_label.pack(side='left', padx=(5,0)) # Count on the left
        self.send_btn.pack(side='right') # Send button on the right
        
        # Pack the chat box LAST, so it expands to fill the remaining space.
        self.chat_box.pack(side='top', expand=True, fill='both', pady=(0, 5))


    # --- display_message ---
    def display_message(self, msg):
        """Safely displays a message in the chat box."""
        try:
            if self.root.winfo_exists() and self.chat_box.winfo_exists():
                self.chat_box.config(state='normal')
                
                if msg.startswith("[System]"):
                    # Insert system messages with the 'system' tag
                    self.chat_box.insert(tk.END, f"{msg}\n", "system")
                elif ": " in msg:
                    # Split user messages and apply 'username' and 'message' tags
                    try:
                        username, message = msg.split(": ", 1)
                        self.chat_box.insert(tk.END, f"{username}: ", "username")
                        self.chat_box.insert(tk.END, f"{message}\n", "message")
                    except ValueError:
                        # Fallback for unexpected format
                        self.chat_box.insert(tk.END, f"{msg}\n", "message")
                else:
                    # Fallback for any other message
                    self.chat_box.insert(tk.END, f"{msg}\n", "message")
                    
                self.chat_box.config(state='disabled')
                self.chat_box.yview(tk.END) # Auto-scroll
        except tk.TclError:
             pass # Ignore if widgets are destroyed

    # --- receive_chat ---
    def receive_chat(self):
        print("--- [CHAT] Receive thread started.")
        while self.is_connected:
            try:
                msg_bytes = self.chat_socket.recv(1024)
                if not msg_bytes:
                    print("[Receive Chat Info] Server closed connection.")
                    break
                
                decoded_msg = msg_bytes.decode('utf-8', 'ignore')
                if not decoded_msg: continue

                # --- Handle System Messages ---
                if decoded_msg.startswith("__USER_JOINED__||"):
                    parts = decoded_msg.split('||', 2)
                    if len(parts) == 3:
                        _, uuid_str, username = parts
                        if uuid_str != self.client_uuid:
                             print(f"[Chat] User Joined: {username} ({uuid_str})")
                             self.uuid_to_username[uuid_str] = username
                             self.root.after(0, self.display_message, f"[System] {username} joined the call.")
                             # Presence sync will handle adding widgets
                    continue

                elif decoded_msg.startswith("__USER_LEFT__||"):
                    parts = decoded_msg.split('||', 1)
                    if len(parts) == 2:
                         uuid_str = parts[1]
                         username = self.uuid_to_username.pop(uuid_str, uuid_str[:8]+"...")
                         print(f"[Chat] User Left: {username} ({uuid_str})")
                         self.root.after(0, self.display_message, f"[System] {username} left the call.")
                         # Presence sync will handle removing widgets
                    continue

                # --- Handle Regular Chat Message ---
                self.root.after(0, self.display_message, decoded_msg)
                # (!!!) NEW: Set notification
                self.root.after(0, self._set_notification_state, 'chat', True)

            except ConnectionResetError:
                 if self.is_connected:
                      print("[Receive Chat Error] Connection reset.")
                 break
            except OSError as e:
                 if self.is_connected: print(f"[Receive Chat Error] Socket closed: {e}"); break
            except Exception as e:
                if self.is_connected:
                    print(f"[Receive Chat Error] General: {e}")
                break
        print("--- [CHAT] Receive thread finished.")

    # --- send_chat_event ---
    def send_chat_event(self, event):
        self.send_chat()

    # --- send_chat ---
    def send_chat(self):
        """Sends a message typed by the user (sends *only* the message)."""
        msg = self.msg_entry.get().strip()
        
        # (!!!) NEW: Final length check
        if len(msg) > CHAT_MESSAGE_LIMIT:
            msg = msg[:CHAT_MESSAGE_LIMIT]
            
        if msg and self.is_connected and self.chat_socket:
            try:
                # Server will prepend username based on registered connection
                self.chat_socket.sendall(msg.encode('utf-8'))
                self.msg_entry.delete(0, tk.END)
                # (!!!) NEW: Reset character count after send
                self.update_chat_count()
            except OSError as e:
                print(f"[Send Chat Error] Socket closed: {e}")
            except Exception as e:
                print(f"[Send Chat Error] {e}")


    # ----------------- FILE -----------------

    # --- build_file_ui ---
    def build_file_ui(self, parent_frame):
        # (!!!) NEW: Frame for buttons
        button_frame = ttk.Frame(parent_frame, style="TFrame")
        button_frame.pack(side='top', fill='x', pady=(10, 5))
        
        self.upload_btn = ttk.Button(button_frame, text="Upload", command=self.upload_file, style="Small.TButton")
        self.upload_btn.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        self.download_btn = ttk.Button(button_frame, text="Download", command=self.download_file, style="Small.TButton")
        self.download_btn.pack(side='left', fill='x', expand=True, padx=5)

        self.file_list_label = ttk.Label(parent_frame, text="Available Files (on Server):") # (!!!) MODIFIED: Text
        self.file_list_label.pack(pady=(5,0), anchor='w')
        
        self.file_list = tk.Listbox(
            parent_frame, bg=self.BG_SECONDARY, fg=self.FG_TEXT,
            height=15, borderwidth=0, highlightthickness=0, relief="flat",
            selectbackground=self.ACCENT_PRIMARY, 
            selectforeground=self.ACCENT_PRIMARY_FG,
            width=1 
        )
        self.file_list.pack(expand=True, fill='both', pady=(5,0))
        
        # (!!!) NEW: Bind double-click to download
        self.file_list.bind('<Double-1>', self.download_file_event)

        # --- Create Downloads directory ---
        self.download_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'CollabSuite')
        try:
            os.makedirs(self.download_dir, exist_ok=True)
        except OSError as e:
             print(f"[File UI Error] Could not create download directory: {e}")
             self.download_dir = os.path.join(os.path.expanduser('~'), 'Downloads') # Fallback
             
        # (!!!) --- NEW: UPLOAD PROGRESS WIDGETS (Hidden by default) --- (!!!)
        
        # Class-level variables to control the widgets
        self.upload_status_var = tk.StringVar(value="")
        self.upload_progress_var = tk.DoubleVar(value=0)
        
        # Frame to hold the progress widgets
        self.upload_progress_frame = ttk.Frame(parent_frame, style="TFrame")
        # Don't pack it yet, it's hidden!
        
        status_label = ttk.Label(self.upload_progress_frame, textvariable=self.upload_status_var, style="TLabel", font=('Segoe UI', 9))
        status_label.pack(fill='x', padx=5)
        
        progress_bar = ttk.Progressbar(self.upload_progress_frame, variable=self.upload_progress_var, maximum=100)
        progress_bar.pack(fill='x', padx=5, pady=(2, 5))
        
        # We pack the frame here so it exists, then immediately hide it.
        self.upload_progress_frame.pack(side='bottom', fill='x', pady=(5,0))
        self.upload_progress_frame.pack_forget()

    # (!!!) --- NEW: PARTICIPANTS UI --- (!!!)
    def build_participants_ui(self, parent_frame):
        self.participants_list_label = ttk.Label(parent_frame, text="Participants (0):", style="TLabel")
        self.participants_list_label.pack(pady=(10,5), anchor='w', padx=5)
        
        self.participants_list = tk.Listbox(
            parent_frame, bg=self.BG_SECONDARY, fg=self.FG_TEXT,
            height=15, borderwidth=0, highlightthickness=0, relief="flat",
            selectbackground=self.ACCENT_PRIMARY, 
            selectforeground=self.ACCENT_PRIMARY_FG,
            width=1 
        )
        self.participants_list.pack(expand=True, fill='both', pady=(5,0))

    def update_participants_list_ui(self):
        """ (!!!) NEW: Clears and repopulates the participant list. """
        if not hasattr(self, 'participants_list') or not self.participants_list.winfo_exists():
            return # UI not built or destroyed

        try:
            self.participants_list.delete(0, tk.END)
            
            # self.uuid_to_username is the source of truth from PRESENCE packets
            # We create a new list to avoid issues if the dict changes during iteration
            all_usernames = list(self.uuid_to_username.values())
            
            local_user_formatted = f"You ({self.username})"
            
            display_list = []
            for name in all_usernames:
                # Check if the name from the server list is our own
                if name == self.username:
                    # If it is, add our special "You" tag
                    if local_user_formatted not in display_list:
                         display_list.append(local_user_formatted)
                else:
                    display_list.append(name)
            
            # Fallback in case PRESENCE hasn't listed us yet
            if local_user_formatted not in display_list:
                 display_list.append(local_user_formatted)
                 
            display_list.sort() # Sort alphabetically

            for name in display_list:
                self.participants_list.insert(tk.END, name)
            
            # Update label with count
            count = len(display_list)
            self.participants_list_label.config(text=f"Participants ({count}):")

        except Exception as e:
            print(f"[Update Participants List Error] {e}")

    # --- upload_file ---
    def upload_file(self):
        if not self.is_connected:
            return

        file_path = filedialog.askopenfilename()
        if not file_path: return

        try:
            fname = os.path.basename(file_path)
            fname = "".join(c if c.isalnum() or c in (' ', '.', '-', '_') else '_' for c in fname).strip()
            if not fname: fname = "uploaded_file"
            
            file_size = os.path.getsize(file_path)
            # (!!!) MODIFIED: Set to 10GB Limit
            if file_size > 1024*1024*1024*10: # 10GB Limit
                messagebox.showerror("File Too Large", "File size cannot exceed 10GB.")
                return

            # Prepend sender username
            fname_with_sender = f"[{self.username}] {fname}"

            # (!!!) --- NEW NON-BLOCKING LOGIC --- (!!!)
            
            # 1. Reset and show the progress bar in the file panel
            self.upload_progress_var.set(0)
            self.upload_status_var.set(f"Starting: {fname}...")
            self.upload_progress_frame.pack(side='bottom', fill='x', pady=(5,0))
            
            # 2. Automatically switch to the file panel to show progress
            self.show_side_panel_view('files')
            
            # 3. Start the thread (it will use the class variables we just set)
            threading.Thread(target=self._upload_file_thread, 
                             args=(file_path, fname_with_sender, file_size), 
                             daemon=True).start()
            
            # (!!!) No more blocking popup! (!!!)

        except FileNotFoundError:
            messagebox.showerror("File Error", "File not found.")
        except Exception as e:
            messagebox.showerror("File Upload Error", f"An error occurred:\n{e}")
            print(f"[Upload File Error] {e}")

    def _upload_file_thread(self, file_path, fname_with_sender, file_size): # (!!!) MODIFIED: No UI args
        """ (!!!) MODIFIED THREADED FUNCTION: Handles upload and reports progress to class variables. """
        temp_sock = None
        try:
            # (!!!) NEW: Update status using class variable
            self.root.after(0, self.upload_status_var.set, "Connecting...")

            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_sock.settimeout(10) # 10 second timeout
            temp_sock.connect((self.server_ip, FILE_DATA_PORT))
            
            # 1. Send UPLOAD header
            header_str = f"__UPLOAD__||{fname_with_sender}||{file_size}"
            header_bytes = header_str.encode('utf-8')
            padded_header = header_bytes + b' ' * (1024 - len(header_bytes))
            temp_sock.sendall(padded_header)

            # 2. Wait for ACK
            self.root.after(0, self.upload_status_var.set, "Waiting for server... [0%/100%]")
            ack = temp_sock.recv(1024)
            if ack != b"__ACK_UPLOAD__":
                print(f"[UPLOAD] Server did not ACK. Received: {ack}")
                raise Exception("Server rejected upload request.")
            
            print(f"[UPLOAD] Server ACK received. Sending {file_size} bytes...")
            self.root.after(0, self.upload_status_var.set, "Uploading... [0%/100%]")
            
            # 3. Send file data
            temp_sock.settimeout(60) # Longer timeout for data
            with open(file_path, 'rb') as f:
                bytes_sent = 0
                while bytes_sent < file_size:
                    chunk = f.read(1024*1024) # (!!!) MODIFIED: 1MB Chunks
                    if not chunk:
                        break # End of file
                    temp_sock.sendall(chunk)
                    bytes_sent += len(chunk)
                    
                    # (!!!) --- NEW: Calculate and send progress --- (!!!)
                    if file_size > 0:
                        percent = (bytes_sent / file_size) * 100
                        # Use root.after to safely update Tkinter vars from the thread
                        self.root.after(0, self.upload_progress_var.set, percent)
                        self.root.after(0, self.upload_status_var.set, f"Uploading... [{int(percent)}%/100%]")
            
            if file_size == 0: # Handle zero-byte files
                self.root.after(0, self.upload_progress_var.set, 100)
                self.root.after(0, self.upload_status_var.set, "Uploading... [100%/100%]")

            print(f"[UPLOAD] Finished sending '{fname_with_sender}'.")
            # The server will now broadcast __FILE_ADDED__ to all clients

        except socket.timeout:
            print(f"[UPLOAD] Socket timeout for '{fname_with_sender}'")
            self.root.after(0, messagebox.showerror, "Upload Failed", "Upload timed out.", parent=self.root)
        except Exception as e:
            print(f"[UPLOAD] Error: {e}")
            self.root.after(0, messagebox.showerror, "Upload Failed", f"An error occurred:\n{e}", parent=self.root)
        finally:
            # (!!!) --- NEW: Always hide the progress bar --- (!!!)
            # Add a small delay so the user can see 100%
            time.sleep(0.5) 
            self.root.after(0, self.upload_progress_var.set, 0)
            self.root.after(0, self.upload_status_var.set, "")
            self.root.after(0, self.upload_progress_frame.pack_forget)
            
            if temp_sock:
                try: temp_sock.close()
                except: pass
    
    def download_file_event(self, event=None):
        """ (!!!) NEW: Helper for double-click bind """
        self.download_file()

    def download_file(self):
        """ (!!!) NEW: Downloads the selected file from the server. """
        if not self.is_connected:
            return

        try:
            selected_indices = self.file_list.curselection()
            if not selected_indices:
                messagebox.showwarning("No File Selected", "Please select a file from the list to download.", parent=self.root)
                return
            
            selected_filename = self.file_list.get(selected_indices[0])
            
            # Ask user where to save
            save_path = filedialog.asksaveasfilename(
                parent=self.root,
                initialdir=self.download_dir,
                initialfile=selected_filename.split('] ')[-1], # Suggest clean filename
                title="Save File As..."
            )
            
            if not save_path:
                return # User cancelled
            
            # (!!!) Run the entire download in a new thread
            threading.Thread(target=self._download_file_thread,
                             args=(selected_filename, save_path),
                             daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Download Error", f"Could not start download:\n{e}", parent=self.root)
    
    def _download_file_thread(self, filename_to_download, save_path):
        """ (!!!) NEW THREADED FUNCTION: Handles the entire download transaction. """
        temp_sock = None
        try:
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_sock.settimeout(10)
            temp_sock.connect((self.server_ip, FILE_DATA_PORT))
            
            # 1. Send DOWNLOAD header (padded to 1024)
            header_str = f"__DOWNLOAD__||{filename_to_download}"
            header_bytes = header_str.encode('utf-8')
            padded_header = header_bytes + b' ' * (1024 - len(header_bytes))
            temp_sock.sendall(padded_header)

            # 2. Wait for ACK
            ack_data = temp_sock.recv(1024)
            if ack_data.startswith(b"__ACK_DOWNLOAD__||"):
                parts = ack_data.split(b"||", 1)
                file_size = int(parts[1].decode('utf-8'))
            elif ack_data == b"__ERR_NO_FILE__":
                raise Exception("File not found on server.")
            else:
                raise Exception(f"Unknown server response: {ack_data}")
                
            print(f"[DOWNLOAD] Server ACK. Expecting {file_size} bytes for '{filename_to_download}'")
            
            # 3. Send CLIENT_READY
            temp_sock.sendall(b"__CLIENT_READY__")
            
            # 4. Receive file data
            temp_sock.settimeout(60) # Longer timeout
            bytes_received = 0
            with open(save_path, 'wb') as f:
                while bytes_received < file_size:
                    chunk_size = min(1024*1024, file_size - bytes_received)
                    chunk = temp_sock.recv(chunk_size)
                    if not chunk:
                        raise ConnectionError("Server disconnected during download")
                    f.write(chunk)
                    bytes_received += len(chunk)
                    
            if bytes_received == file_size:
                print(f"[DOWNLOAD] Successfully saved to '{save_path}'")
                self.root.after(0, messagebox.showinfo, "Download Complete", f"File saved successfully:\n{save_path}", parent=self.root)
            else:
                raise Exception("File size mismatch.")
                
        except socket.timeout:
            print(f"[DOWNLOAD] Socket timeout for '{filename_to_download}'")
            self.root.after(0, messagebox.showerror, "Download Failed", "Download timed out.", parent=self.root)
        except Exception as e:
            print(f"[DOWNLOAD] Error: {e}")
            self.root.after(0, messagebox.showerror, "Download Failed", f"An error occurred:\n{e}", parent=self.root)
            if os.path.exists(save_path): # Clean up partial
                try: os.remove(save_path)
                except: pass
        finally:
            if temp_sock:
                try: temp_sock.close()
                except: pass

    # --- receive_file ---
    def receive_file(self):
        """
        (!!!) MODIFIED: Listens on the *control* socket (9996) for file list updates.
        """
        print("--- [FILE CONTROL] Receive thread started.")
        buffer = ""
        while self.is_connected:
            try:
                data_bytes = self.file_socket.recv(4096)
                if not data_bytes:
                    print("[FILE CONTROL] Server closed connection.")
                    break
                
                buffer += data_bytes.decode('utf-8', 'ignore')

                # (!!!) --- NEWEST CORRECTED PARSER (Splits on __END__) --- (!!!)
                while "__END__" in buffer:
                    # Split at the first terminator
                    message, rest = buffer.split("__END__", 1)
                    buffer = rest # Keep the rest for the next loop

                    if not message.startswith("__"):
                        # This is a fragment or garbage, ignore it
                        continue 
                    
                    # --- Process the Full Message ---
                    if message.startswith("__FILE_LIST__||"):
                        payload = message.replace("__FILE_LIST__||", "")
                        file_list = payload.split("||") if payload else []
                        self.root.after(0, self.update_file_list_ui, file_list)
                        print(f"[FILE CONTROL] Received initial file list ({len(file_list)} files)")

                    elif message.startswith("__FILE_ADDED__||"):
                        filename = message.replace("__FILE_ADDED__||", "")
                        if filename:
                            self.root.after(0, self.add_to_file_list, filename)
                            # (!!!) NEW: Set notification
                            self.root.after(0, self._set_notification_state, 'files', True)
                            print(f"[FILE CONTROL] Received new file: {filename}")
                
                # (!!!) --- END OF NEW PARSER --- (!!!)

            except (ConnectionResetError, OSError) as e:
                if self.is_connected: print(f"[FILE CONTROL] Connection error: {e}")
                break
            except Exception as e:
                if self.is_connected: 
                    print(f"[FILE CONTROL] Parse Error: {e}. Buffer: {buffer[:100]}")
                    buffer = "" # Clear corrupt buffer
                    time.sleep(0.1)
        
        print("--- [FILE CONTROL] Receive thread finished.")

    def update_file_list_ui(self, file_list):
        """ (!!!) NEW HELPER: Clears and repopulates the file listbox. """
        try:
            if not self.file_list.winfo_exists(): return
            self.file_list.delete(0, tk.END)
            for f in file_list:
                if f: self.file_list.insert(tk.END, f)
        except Exception as e:
            print(f"[Update File List Error] {e}")

    # --- _recv_all ---
    # ... (This function is still needed for receive_chat) ...

    # --- _skip_data ---
    # ... (This function is no longer needed by receive_file) ...

    # --- add_to_file_list ---
    # ... (This function is still used, keep it) ...

    # --- _recv_all ---
    def _recv_all(self, sock, n):
        """Helper to receive exactly n bytes from a blocking socket."""
        data = bytearray()
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet: raise ConnectionError("Connection closed while receiving data")
            data.extend(packet)
        return bytes(data)

    # --- _skip_data ---
    def _skip_data(self, sock, n):
        """Helper to consume n bytes from a socket (e.g., to skip a large file)."""
        bytes_skipped = 0
        try:
            while bytes_skipped < n:
                chunk_size = min(4096, n - bytes_skipped)
                chunk = sock.recv(chunk_size)
                if not chunk: break
                bytes_skipped += len(chunk)
        except Exception as e:
             print(f"[Skip Data Error] {e}")

    # --- add_to_file_list ---
    def add_to_file_list(self, filename):
        """Adds filename to the listbox in the UI."""
        try:
            if self.root.winfo_exists() and self.file_list.winfo_exists():
                self.file_list.insert(tk.END, f"{filename}")
                self.file_list.yview(tk.END)
        except tk.TclError:
              pass

    # ----------------- CLEANUP -----------------

    # --- on_closing ---
    def on_closing(self):
        """Handles window close event."""
        if not self.is_connected:
             try: self.root.destroy()
             except: pass
             return

        if messagebox.askokcancel("Quit", "Are you sure you want to disconnect and quit?"):
            print("Disconnecting...")
            self.is_connected = False # Signal all threads to stop

            self.video_sending = False
            self.audio_sending = False
            self.screen_sharing = False

            time.sleep(0.3) # Give threads time to see flag

            # --- Release Media ---
            if self.video_capture:
                print("Releasing video capture...")
                try: self.video_capture.release()
                except Exception as e: print(f"[Cleanup Error] Releasing video: {e}")
            if self.sending_audio_stream:
                 try:
                      print("Closing sending audio stream...")
                      if self.sending_audio_stream.is_active(): self.sending_audio_stream.stop_stream()
                      self.sending_audio_stream.close()
                 except Exception as e: print(f"[Cleanup Error] Closing send audio: {e}")
            if self.receiving_audio_stream:
                 try:
                      print("Closing receiving audio stream...")
                      if self.receiving_audio_stream.is_active(): self.receiving_audio_stream.stop_stream()
                      self.receiving_audio_stream.close()
                 except Exception as e: print(f"[Cleanup Error] Closing recv audio: {e}")
            try:
                print("Terminating PyAudio...")
                self.p_audio.terminate()
            except Exception as e: print(f"[Cleanup Error] Terminating PyAudio: {e}")

            # --- Close Sockets ---
            print("Closing sockets...")
            sockets_to_close = [
                ('Chat', self.chat_socket), 
                ('File', self.file_socket),
            ]
            # Add feedback socket only if it's a real socket
            if isinstance(self.feedback_socket, socket.socket):
                sockets_to_close.append(('Feedback', self.feedback_socket))

            for sock_name, sock in sockets_to_close:
                if sock:
                    print(f"Closing {sock_name} TCP socket...")
                    try: sock.shutdown(socket.SHUT_RDWR)
                    except (OSError, AttributeError): pass
                    try: sock.close()
                    except: pass
                    
            for sock_name, sock in [('Video', self.video_socket), ('Audio', self.audio_socket), ('Screen', self.screen_socket)]:
                 if sock:
                      print(f"Closing {sock_name} UDP socket...")
                      try: sock.close()
                      except: pass

            print("Destroying root window...")
            try:
                if self.root.winfo_exists(): self.root.destroy()
                print("Root window destroyed.")
            except tk.TclError:
                 print("Root window already destroyed (TclError).")


# ------------------ RUN ------------------
if __name__ == "__main__":
    print("Starting application...")
    root = tk.Tk()
    app = CollabClient(root)
    root.mainloop()
    print("Application finished.")

