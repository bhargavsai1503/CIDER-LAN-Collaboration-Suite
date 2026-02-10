import socket
import threading
import struct
import time
import uuid # Import UUID library
from datetime import datetime # (!!!) NEW: For feedback logging
import csv # (!!!) NEW: For feedback CSV
import os.path # (!!!) NEW: To check if CSV exists
import os # (!!!) NEW: For file storage
import shutil # (!!!) NEW: For file storage

# --- CONFIGURATION ---
SERVER_HOST = "0.0.0.0"
VIDEO_PORT = 9999
AUDIO_PORT = 9998
CHAT_PORT = 9997
FILE_PORT = 9996        # (!!!) MODIFIED: This is now the FILE *CONTROL* port
FILE_DATA_PORT = 9993   # (!!!) NEW: This is for UPLOAD/DOWNLOAD transactions
SCREEN_PORT = 9995
FEEDBACK_PORT = 9994 
BUFFER_SIZE = 65536 * 2

# (!!!) NEW: Server-side file storage
SERVER_FILE_STORAGE = "server_files" 

# (!!!) NEW: Feedback log file
FEEDBACK_LOG_FILE = "cider_feedback.csv" 

# --- CLIENT LISTS & LOCKS ---
clients_chat = []
clients_file = [] # (!!!) MODIFIED: List of *control* connections
# --- !! UDP Client Tracking Updated (Stores username) !! ---
clients_video = {}
clients_audio = {}
clients_screen = {}
uuid_to_addr = {}
# --- !! End Update !! ---

# (!!!) NEW: In-memory list of available files
# Map { display_name_with_sender: safe_filename_on_disk }
available_files = {} 
available_files_lock = threading.Lock()


chat_lock = threading.Lock()
file_lock = threading.Lock() # (!!!) MODIFIED: Lock for clients_file list
video_lock = threading.Lock()
audio_lock = threading.Lock()
screen_lock = threading.Lock()
uuid_map_lock = threading.Lock() 
feedback_log_lock = threading.Lock() 


# --- !! NEW: Global Sockets for broadcasting presence/commands !! ---
s_video = None
s_audio = None
s_screen = None
# --- !! End NEW !! ---


# --- HELPER: BROADCAST (TCP) ---
# --- (Modified from server8www.py to use client info for disconnects) ---
def broadcast_tcp(clients_list, lock, msg, sender_conn, include_sender=True):
    """
    Broadcasts a message to all clients in a TCP list.
    Can optionally skip the original sender.
    Handles removal correctly based on the list type (chat vs file).
    """
    with lock:
        to_remove = []
        current_clients = list(clients_list) # Make a copy

        for client_conn in current_clients:
            if not include_sender and client_conn == sender_conn:
                continue

            try:
                client_conn.sendall(msg)
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                peername = "unknown"
                try: peername = client_conn.getpeername()
                except OSError: pass
                print(f"[TCP DISCONNECT] Error sending to {peername}: {e}")
                to_remove.append(client_conn)
            except Exception as e:
                 peername = "unknown"
                 try: peername = client_conn.getpeername()
                 except OSError: pass
                 print(f"[TCP BROADCAST ERROR] Unexpected error for {peername}: {e}")
                 to_remove.append(client_conn)

        # --- Removal Logic ---
        for conn in to_remove:
            if conn in clients_list:
                peername = "unknown (already closed?)"
                try: peername = conn.getpeername()
                except OSError: pass
                print(f"[TCP DISCONNECT] Removing dead client {peername}")
                clients_list.remove(conn)

                # --- !! Special handling for chat clients !! ---
                if clients_list is clients_chat:
                    with chat_info_lock: # Assuming chat_info_lock exists
                         info = chat_client_info.pop(conn, None) # Assuming chat_client_info exists
                         if info:
                             print(f"[CHAT] Cleaned up info for disconnected user: {info.get('username','?')}")
                             # Broadcast leave message if chat user disconnected abruptly
                             leave_msg = f"__USER_LEFT__||{info['uuid']}"
                             threading.Thread(target=_broadcast_after_removal, args=(clients_chat, chat_lock, leave_msg.encode('utf-8'), conn), daemon=True).start()
                
                # (!!!) NEW: Special handling for file clients (just remove)
                elif clients_list is clients_file:
                     print(f"[FILE CONTROL] Cleaned up disconnected client {peername}")


                try: conn.close()
                except: pass

# --- !! NEW HELPER: Broadcast after removal to avoid re-locking !! ---
def _broadcast_after_removal(client_list, lock, msg, removed_conn):
     time.sleep(0.01)
     broadcast_tcp(client_list, lock, msg, removed_conn, include_sender=False)


# --- HELPER: BROADCAST (UDP) ---
def broadcast_udp(clients_dict, lock, data_to_send, original_client_uuid, server_socket, packet_type_name):
    header = f"{packet_type_name}||{original_client_uuid}||".encode('utf-8')
    full_packet = header + data_to_send

    if len(full_packet) > BUFFER_SIZE:
         print(f"[{packet_type_name} WARN] Packet too large ({len(full_packet)} bytes) for {original_client_uuid}. Skipping.")
         return

    with lock:
        current_addrs = list(clients_dict.keys())
        for addr_tuple in current_addrs:
            try:
                server_socket.sendto(full_packet, addr_tuple)
            except OSError as e:
                 print(f"[{packet_type_name} UDP SEND ERROR] OS Error sending to {addr_tuple}: {e}")
            except Exception as e:
                print(f"[{packet_type_name} UDP SEND ERROR] Unexpected error sending to {addr_tuple}: {e}")

# --- !! NEW HELPER: BROADCAST COMMAND (UDP) !! ---
def broadcast_command_udp(clients_dict, lock, command_packet, server_socket, command_name):
    with lock:
        current_addrs = list(clients_dict.keys())
        for addr_tuple in current_addrs:
            try:
                server_socket.sendto(command_packet, addr_tuple)
            except OSError as e:
                 print(f"[{command_name} UDP SEND ERROR] OS Error sending to {addr_tuple}: {e}")
            except Exception as e:
                print(f"[{command_name} UDP SEND ERROR] Unexpected error sending to {addr_tuple}: {e}")

# --- CHAT SERVER (TCP) ---
chat_client_info = {} 
chat_info_lock = threading.Lock() 

def handle_chat_client(conn, addr):
    print(f"[CHAT] Connected: {addr}")
    addr_str = str(addr)
    client_uuid = None
    client_username = None

    try:
        while True:
            msg_bytes = conn.recv(1024)
            if not msg_bytes:
                print(f"[CHAT] Client {addr_str} disconnected gracefully.")
                break

            msg = msg_bytes.decode('utf-8', 'ignore')
            if not msg: continue

            if msg.startswith("__REGISTER_USER__||"):
                parts = msg.split('||', 2)
                if len(parts) == 3:
                    _, client_uuid, client_username = parts
                    print(f"[CHAT] User registered: {client_username} ({client_uuid}) from {addr_str}")
                    with chat_info_lock:
                        chat_client_info[conn] = {'uuid': client_uuid, 'username': client_username}

                    join_msg = f"__USER_JOINED__||{client_uuid}||{client_username}"
                    broadcast_tcp(clients_chat, chat_lock, join_msg.encode('utf-8'), conn, include_sender=True)

                    with chat_info_lock:
                        for other_conn, info in chat_client_info.items():
                            if other_conn != conn:
                                existing_user_msg = f"__USER_JOINED__||{info['uuid']}||{info['username']}"
                                try: conn.sendall(existing_user_msg.encode('utf-8'))
                                except Exception as e: print(f"[CHAT] Failed to send existing list to {addr_str}: {e}")
                    continue 

            if not client_uuid: 
                print(f"[CHAT] Ignoring message from unregistered client {addr_str}")
                continue

            full_msg = f"{client_username}: {msg}" # Prepend username
            broadcast_tcp(clients_chat, chat_lock, full_msg.encode('utf-8'), conn, include_sender=True)

    except ConnectionResetError: print(f"[CHAT] Client {addr_str} reset connection.")
    except OSError as e: print(f"[CHAT] OS Error for {addr_str}: {e}")
    except Exception as e: print(f"[CHAT] Unexpected error for {addr_str}: {e}")
    finally:
        print(f"[CHAT] Cleaning up connection for {addr_str}")
        with chat_lock:
            if conn in clients_chat: clients_chat.remove(conn)

        with chat_info_lock:
            info = chat_client_info.pop(conn, None)
            if info:
                print(f"[CHAT] User left: {info['username']} ({info['uuid']})")
                leave_msg = f"__USER_LEFT__||{info['uuid']}"
                threading.Thread(target=_broadcast_after_removal, args=(clients_chat, chat_lock, leave_msg.encode('utf-8'), conn), daemon=True).start()

        try: conn.close()
        except: pass
        print(f"[CHAT] Disconnected: {addr_str}")

def chat_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((SERVER_HOST, CHAT_PORT))
        s.listen(10)
        print(f"[CHAT] TCP Listening on port {CHAT_PORT}")
    except Exception as e:
        print(f"[ERROR] Failed to start CHAT server on {SERVER_HOST}:{CHAT_PORT}: {e}")
        return

    while True:
        try:
            conn, addr = s.accept()
            with chat_lock: clients_chat.append(conn)
            threading.Thread(target=handle_chat_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
             print(f"[CHAT ACCEPT ERROR] {e}")
             time.sleep(1)


# (!!!) --- MODIFIED: FILE *CONTROL* SERVER (TCP) --- (!!!)
def handle_file_client(conn, addr):
    """
    Handles a persistent connection for file *control* (list sync, add announcements).
    """
    print(f"[FILE CONTROL] Connected: {addr}")
    addr_str = str(addr)
    
    # 1. Send the current list of files to the new client
    try:
        with available_files_lock:
            # Get the *display names* (the keys)
            file_list = list(available_files.keys()) 
        
        payload = "||".join(file_list)
        list_msg = f"__FILE_LIST__||{payload}__END__"
        conn.sendall(list_msg.encode('utf-8'))
        print(f"[FILE CONTROL] Sent file list to {addr_str} ({len(file_list)} files)")

    except Exception as e:
        print(f"[FILE CONTROL] Error sending file list to {addr_str}: {e}")
        with file_lock:
            if conn in clients_file: clients_file.remove(conn)
        try: conn.close()
        except: pass
        return

    # 2. Keep connection open to receive broadcast announcements
    #    (and to detect disconnects)
    try:
        while True:
            data = conn.recv(1024) # Wait for disconnect
            if not data:
                print(f"[FILE CONTROL] Client {addr_str} disconnected gracefully.")
                break
            else:
                # We don't expect any other messages on this port
                print(f"[FILE CONTROL] Received unexpected data from {addr_str}. Ignoring.")
                
    except ConnectionResetError: print(f"[FILE CONTROL] Client {addr_str} reset connection.")
    except OSError as e: print(f"[FILE CONTROL] OS Error for {addr_str}: {e}")
    except Exception as e: print(f"[FILE CONTROL] Unexpected Error for {addr_str}: {e}")
    finally:
        print(f"[FILE CONTROL] Cleaning up connection for {addr_str}")
        with file_lock:
            if conn in clients_file: clients_file.remove(conn)
        try: conn.close()
        except: pass
        print(f"[FILE CONTROL] Disconnected: {addr_str}")

def file_server():
    """
    Listens for FILE *CONTROL* connections (Port 9996).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((SERVER_HOST, FILE_PORT))
        s.listen(10)
        print(f"[FILE CONTROL] TCP Listening on port {FILE_PORT}")
    except Exception as e:
        print(f"[ERROR] Failed to start FILE CONTROL server on {SERVER_HOST}:{FILE_PORT}: {e}")
        return

    while True:
        try:
            conn, addr = s.accept()
            with file_lock: clients_file.append(conn)
            threading.Thread(target=handle_file_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
             print(f"[FILE CONTROL ACCEPT ERROR] {e}")
             time.sleep(1)


# (!!!) --- NEW: FILE *DATA* SERVER (TCP) --- (!!!)
def handle_file_data_client(conn, addr):
    """
    Handles a *transactional* connection for UPLOAD or DOWNLOAD.
    One connection = One action.
    """
    print(f"[FILE DATA] Connection from: {addr}")
    addr_str = str(addr)
    try:
        # 1. Read a fixed-size header to determine action
        header_data = conn.recv(1024) # Client must pad to 1024
        if not header_data:
            print(f"[FILE DATA] No header from {addr_str}. Closing.")
            return
            
        header_str = header_data.decode('utf-8', 'ignore').strip()
        
        # --- HANDLE UPLOAD ---
        if header_str.startswith("__UPLOAD__||"):
            parts = header_str.split('||', 2)
            if len(parts) < 3:
                print(f"[FILE DATA] Malformed UPLOAD header from {addr_str}")
                return
            
            filename_with_sender = parts[1]
            try:
                file_size = int(parts[2])
            except ValueError:
                print(f"[FILE DATA] Invalid filesize from {addr_str}")
                return
            
            if not (0 <= file_size <= 1024*1024*1024*10): # 10GB Limit
                 print(f"[FILE DATA] Invalid file size {file_size} from {addr_str}")
                 return

            # Sanitize filename for saving
            filename_part = filename_with_sender.split('] ')[-1] # Get "file.txt" from "[User] file.txt"
            safe_filename_part = "".join(c if c.isalnum() or c in ('.', '-', '_') else '_' for c in filename_part)
            if not safe_filename_part: safe_filename_part = "uploaded_file"
            
            # Create a unique filename for storage
            safe_filename_on_disk = f"{uuid.uuid4()}_{safe_filename_part}"
            save_path = os.path.join(SERVER_FILE_STORAGE, safe_filename_on_disk)

            print(f"[FILE DATA] Receiving '{filename_with_sender}' ({file_size} bytes) from {addr_str} -> {safe_filename_on_disk}")

            # 2. Send ACK to client to start sending data
            conn.sendall(b"__ACK_UPLOAD__")

            # 3. Receive file data
            bytes_received = 0
            try:
                with open(save_path, 'wb') as f:
                    while bytes_received < file_size:
                        chunk_size = min(1024*1024, file_size - bytes_received)
                        chunk = conn.recv(chunk_size)
                        if not chunk: raise ConnectionError("File client disconnected during upload")
                        f.write(chunk)
                        bytes_received += len(chunk)

                if bytes_received == file_size:
                    print(f"[FILE DATA] Successfully received {safe_filename_on_disk}")
                    # 4. Update the global file list
                    with available_files_lock:
                        available_files[filename_with_sender] = safe_filename_on_disk
                    
                    # 5. Broadcast the update to all *control* clients
                    broadcast_msg = f"__FILE_ADDED__||{filename_with_sender}__END__"
                    broadcast_tcp(clients_file, file_lock, broadcast_msg.encode('utf-8'), None, include_sender=True)
                else:
                    raise ConnectionError("File size mismatch")

            except Exception as e:
                print(f"[FILE DATA] Error receiving file: {e}")
                if os.path.exists(save_path): os.remove(save_path) # Clean up partial

        # --- HANDLE DOWNLOAD ---
        elif header_str.startswith("__DOWNLOAD__||"):
            parts = header_str.split('||', 1)
            if len(parts) < 2:
                print(f"[FILE DATA] Malformed DOWNLOAD header from {addr_str}")
                return
            
            filename_with_sender = parts[1]
            print(f"[FILE DATA] Request for '{filename_with_sender}' from {addr_str}")

            # 2. Find file in our map
            safe_filename_on_disk = None
            with available_files_lock:
                safe_filename_on_disk = available_files.get(filename_with_sender)

            if not safe_filename_on_disk:
                print(f"[FILE DATA] File not found: '{filename_with_sender}'")
                conn.sendall(b"__ERR_NO_FILE__")
                return

            file_path = os.path.join(SERVER_FILE_STORAGE, safe_filename_on_disk)
            
            if not os.path.exists(file_path):
                print(f"[FILE DATA] File missing from disk: '{safe_filename_on_disk}'")
                conn.sendall(b"__ERR_NO_FILE__")
                # Also clean up the map
                with available_files_lock:
                    available_files.pop(filename_with_sender, None)
                return
            
            try:
                # 3. Send ACK with filesize
                file_size = os.path.getsize(file_path)
                conn.sendall(f"__ACK_DOWNLOAD__||{file_size}".encode('utf-8'))

                # 4. Wait for client to be ready
                if conn.recv(1024) == b'__CLIENT_READY__':
                    print(f"[FILE DATA] Sending {file_size} bytes for '{safe_filename_on_disk}'")
                    # 5. Send file data
                    with open(file_path, 'rb') as f:
                        while True:
                            chunk = f.read(1024*1024)
                            if not chunk:
                                break # End of file
                            conn.sendall(chunk)
                    print(f"[FILE DATA] Finished sending '{safe_filename_on_disk}'")
                else:
                    print(f"[FILE DATA] Client not ready. Aborting download.")

            except Exception as e:
                print(f"[FILE DATA] Error sending file: {e}")

        else:
            print(f"[FILE DATA] Unknown command from {addr_str}: {header_str[:100]}...")

    except ConnectionResetError: print(f"[FILE DATA] Client {addr_str} reset connection.")
    except OSError as e: print(f"[FILE DATA] OS Error for {addr_str}: {e}")
    except struct.error as e: print(f"[FILE DATA] Struct error from {addr_str}: {e}")
    except Exception as e: print(f"[FILE DATA] Unexpected Error for {addr_str}: {e}")
    finally:
        try: conn.close()
        except: pass
        print(f"[FILE DATA] Disconnected (Data): {addr_str}")

def file_data_server():
    """
    Listens for FILE *DATA* connections (Port 9993).
    These are transactional (upload/download).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((SERVER_HOST, FILE_DATA_PORT))
        s.listen(10)
        print(f"[FILE DATA] TCP Listening on port {FILE_DATA_PORT}")
    except Exception as e:
        print(f"[ERROR] Failed to start FILE DATA server on {SERVER_HOST}:{FILE_DATA_PORT}: {e}")
        return

    while True:
        try:
            conn, addr = s.accept()
            # No client list, just handle and close
            threading.Thread(target=handle_file_data_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
             print(f"[FILE DATA ACCEPT ERROR] {e}")
             time.sleep(1)
# (!!!) --- END FILE DATA SERVER --- (!!!)


# (!!!) --- NEW: FEEDBACK SERVER (TCP) --- (!!!)
def handle_feedback_client(conn, addr):
    print(f"[FEEDBACK] Connection from: {addr}")
    addr_str = str(addr)
    try:
        header_len_data = conn.recv(4, socket.MSG_WAITALL)
        if not header_len_data or len(header_len_data) < 4:
            print(f"[FEEDBACK] No header from {addr_str}. Closing.")
            return

        report_len = struct.unpack('I', header_len_data)[0]
        if not (0 < report_len < 4096): 
            print(f"[FEEDBACK] Invalid report length ({report_len}) from {addr_str}. Closing.")
            return

        report_data = conn.recv(report_len, socket.MSG_WAITALL)
        if not report_data or len(report_data) < report_len:
            print(f"[FEEDBACK] Incomplete report from {addr_str}. Closing.")
            return
            
        report_str = report_data.decode('utf-8', 'ignore')
        
        if report_str.startswith("__FEEDBACK__||"):
            parts = report_str.split('||', 4)
            if len(parts) == 5:
                _, client_uuid, client_username, timestamp, feedback_msg = parts
                
                log_data = [timestamp, client_username, client_uuid, addr_str, feedback_msg]
                
                with feedback_log_lock:
                    file_exists = os.path.exists(FEEDBACK_LOG_FILE)
                    
                    try:
                        with open(FEEDBACK_LOG_FILE, 'a', encoding='utf-8', newline='') as f:
                            writer = csv.writer(f)
                            if not file_exists:
                                writer.writerow(['Timestamp', 'Username', 'UUID', 'IP_Address', 'Message'])
                            writer.writerow(log_data)
                        
                        print(f"[FEEDBACK] Successfully logged feedback from {client_username} to CSV.")
                        
                    except IOError as e:
                        print(f"[FEEDBACK] CRITICAL: Could not write to CSV file: {e}")
                
            else:
                print(f"[FEEDBACK] Malformed report from {addr_str}: {report_str[:100]}...")
        else:
            print(f"[FEEDBACK] Unknown report format from {addr_str}: {report_str[:100]}...")

    except ConnectionResetError: print(f"[FEEDBACK] Client {addr_str} reset connection.")
    except OSError as e: print(f"[FEEDBACK] OS Error for {addr_str}: {e}")
    except struct.error as e: print(f"[FEEDBACK] Struct error from {addr_str}: {e}")
    except Exception as e: print(f"[FEEDBACK] Unexpected Error for {addr_str}: {e}")
    finally:
        try: conn.close()
        except: pass
        print(f"[FEEDBACK] Disconnected: {addr_str}")

def feedback_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((SERVER_HOST, FEEDBACK_PORT))
        s.listen(10)
        print(f"[FEEDBACK] TCP Listening on port {FEEDBACK_PORT}")
    except Exception as e:
        print(f"[ERROR] Failed to start FEEDBACK server on {SERVER_HOST}:{FEEDBACK_PORT}: {e}")
        return

    while True:
        try:
            conn, addr = s.accept()
            threading.Thread(target=handle_feedback_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
             print(f"[FEEDBACK ACCEPT ERROR] {e}")
             time.sleep(1)
# (!!!) --- END FEEDBACK SERVER --- (!!!)


# --- GENERIC UDP SERVER (Handles REGISTER, KEEPALIVE, STREAM OFF, and Media) ---
def udp_server(port, clients_dict, lock, name):
    global s_video, s_audio, s_screen 

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((SERVER_HOST, port))
        print(f"[{name}] UDP Listening on {port}")
    except Exception as e:
        print(f"[ERROR] Failed to start {name} UDP server on {SERVER_HOST}:{port}: {e}")
        return

    if name == "VIDEO": s_video = s
    elif name == "AUDIO": s_audio = s
    elif name == "SCREEN": s_screen = s

    while True:
        try:
            data, addr_tuple = s.recvfrom(BUFFER_SIZE)
            if not data: continue

            now = time.time()
            delimiter = b'||'

            if data.startswith(b'REGISTER||'):
                try:
                    parts = data.split(b'||', 2)
                    if len(parts) < 3: raise ValueError("Malformed REGISTER")
                    _, uuid_bytes, username_bytes = parts
                    client_uuid = uuid_bytes.decode('utf-8', 'ignore')
                    username = username_bytes.decode('utf-8', 'ignore').strip() or "Guest"
                    uuid.UUID(client_uuid) 

                    print(f"[{name}] Client registered: Addr={addr_tuple}, UUID={client_uuid}, User='{username}'")
                    with lock:
                        clients_dict[addr_tuple] = {'uuid': client_uuid, 'last_seen': now, 'username': username}
                    with uuid_map_lock: uuid_to_addr[client_uuid] = addr_tuple
                except (UnicodeDecodeError, ValueError, IndexError) as e:
                    print(f"[{name} WARN] Invalid REGISTER from {addr_tuple}: {e}")
                    with lock: clients_dict.setdefault(addr_tuple, {'uuid': 'unknown', 'last_seen': now, 'username': 'Unknown'})['last_seen'] = now
                continue 

            elif data.startswith(b'KEEPALIVE||'):
                try:
                    parts = data.split(b'||', 2)
                    if len(parts) < 3: raise ValueError("Malformed KEEPALIVE")
                    _, uuid_bytes, username_bytes = parts
                    client_uuid = uuid_bytes.decode('utf-8', 'ignore')
                    username = username_bytes.decode('utf-8', 'ignore').strip() or "Guest"
                    uuid.UUID(client_uuid) 

                    with lock:
                        if addr_tuple in clients_dict:
                            clients_dict[addr_tuple]['last_seen'] = now
                            clients_dict[addr_tuple]['username'] = username 
                            if clients_dict[addr_tuple]['uuid'] != client_uuid and clients_dict[addr_tuple]['uuid'] != 'unknown':
                                print(f"[{name} WARN] UUID changed for {addr_tuple} via KEEPALIVE: {clients_dict[addr_tuple]['uuid']} -> {client_uuid}")
                            clients_dict[addr_tuple]['uuid'] = client_uuid 
                        else: 
                            print(f"[{name}] New client via KEEPALIVE: Addr={addr_tuple}, UUID={client_uuid}, User='{username}'")
                            clients_dict[addr_tuple] = {'uuid': client_uuid, 'last_seen': now, 'username': username}
                            with uuid_map_lock: uuid_to_addr[client_uuid] = addr_tuple
                except (UnicodeDecodeError, ValueError, IndexError) as e:
                    print(f"[{name} WARN] Invalid KEEPALIVE from {addr_tuple}: {e}")
                    with lock: clients_dict.setdefault(addr_tuple, {'uuid': 'unknown', 'last_seen': now, 'username': 'Unknown'})['last_seen'] = now
                continue 

            elif data.startswith(b'VIDEOCAM_OFF||'):
                try:
                    parts = data.split(b'||', 2)
                    if len(parts) < 2: raise ValueError("Malformed VIDEOCAM_OFF")
                    client_uuid = parts[1].decode('utf-8', 'ignore')
                    uuid.UUID(client_uuid) 
                    print(f"[{name}] Received VIDEOCAM_OFF from {client_uuid[:8]}. Broadcasting STREAM_OFF.")
                    command_packet = f"STREAM_OFF||{client_uuid}||VIDEO".encode('utf-8')
                    if s_video: broadcast_command_udp(clients_video, video_lock, command_packet, s_video, "STREAM_OFF")
                    if s_screen: broadcast_command_udp(clients_screen, screen_lock, command_packet, s_screen, "STREAM_OFF")
                except (UnicodeDecodeError, ValueError, IndexError) as e: print(f"[{name} WARN] Invalid VIDEOCAM_OFF: {e}")
                continue 

            elif data.startswith(b'SCREEN_OFF||'):
                try:
                    parts = data.split(b'||', 2)
                    if len(parts) < 2: raise ValueError("Malformed SCREEN_OFF")
                    client_uuid = parts[1].decode('utf-8', 'ignore')
                    uuid.UUID(client_uuid) 
                    print(f"[{name}] Received SCREEN_OFF from {client_uuid[:8]}. Broadcasting STREAM_OFF.")
                    command_packet = f"STREAM_OFF||{client_uuid}||SCREEN".encode('utf-8')
                    if s_video: broadcast_command_udp(clients_video, video_lock, command_packet, s_video, "STREAM_OFF")
                    if s_screen: broadcast_command_udp(clients_screen, screen_lock, command_packet, s_screen, "STREAM_OFF")
                except (UnicodeDecodeError, ValueError, IndexError) as e: print(f"[{name} WARN] Invalid SCREEN_OFF: {e}")
                continue 

            else:
                if delimiter not in data or data.count(delimiter) < 2:
                    if addr_tuple in clients_dict: print(f"[{name} WARN] Malformed media packet from known client {addr_tuple}: {data[:60]}...")
                    continue 

                try:
                    header_part, uuid_bytes, original_data = data.split(delimiter, 2)
                    packet_type = header_part.decode('utf-8', 'ignore')
                    client_uuid = uuid_bytes.decode('utf-8', 'ignore')
                    uuid.UUID(client_uuid) 
                except (UnicodeDecodeError, ValueError, IndexError) as e:
                    print(f"[{name} WARN] Invalid media header from {addr_tuple}: {e}")
                    continue 

                if packet_type != name:
                    print(f"[{name} WARN] Received '{packet_type}' on '{name}' port from {addr_tuple}. Discarding.")
                    continue

                with lock:
                    if addr_tuple in clients_dict:
                        clients_dict[addr_tuple]['last_seen'] = now
                        if clients_dict[addr_tuple]['uuid'] == 'unknown':
                            clients_dict[addr_tuple]['uuid'] = client_uuid
                            print(f"[{name}] Associated UUID {client_uuid} with {addr_tuple} via media packet.")
                            with uuid_map_lock: uuid_to_addr[client_uuid] = addr_tuple
                        elif clients_dict[addr_tuple]['uuid'] != client_uuid:
                             print(f"[{name} WARN] UUID mismatch for {addr_tuple}: {clients_dict[addr_tuple]['uuid']} != {client_uuid}")
                    else: 
                         print(f"[{name}] New client via media packet: Addr={addr_tuple}, UUID={client_uuid}")
                         clients_dict[addr_tuple] = {'uuid': client_uuid, 'last_seen': now, 'username': 'Unknown'} 
                         with uuid_map_lock: uuid_to_addr[client_uuid] = addr_tuple

                broadcast_udp(clients_dict, lock, original_data, client_uuid, s, packet_type)

        except ConnectionResetError: print(f"[{name} UDP WARN] ConnectionResetError (ignoring)") 
        except OSError as e: print(f"[{name} UDP ERROR] OS Error: {e}") ; time.sleep(0.1)
        except Exception as e: print(f"[{name} UDP ERROR] Unexpected: {e}") ; time.sleep(0.1)

# --- MAIN Thread (Handles Cleanup and Presence Broadcasting) ---
def main():
    print("=== LAN Collaboration Server v17 (Central File Storage) ===")
    global s_video 

    # (!!!) NEW: Create server file storage directory
    try:
        os.makedirs(SERVER_FILE_STORAGE, exist_ok=True)
        print(f"File storage directory: '{SERVER_FILE_STORAGE}'")
    except Exception as e:
        print(f"CRITICAL ERROR: Could not create file storage directory: {e}")
        return

    # Start TCP servers
    threading.Thread(target=chat_server, daemon=True).start()
    threading.Thread(target=file_server, daemon=True).start()     # (!!!) MODIFIED: This is FILE *CONTROL*
    threading.Thread(target=file_data_server, daemon=True).start() # (!!!) NEW: This is FILE *DATA*
    threading.Thread(target=feedback_server, daemon=True).start() 

    # Start UDP servers
    threading.Thread(target=udp_server, args=(VIDEO_PORT, clients_video, video_lock, "VIDEO"), daemon=True).start()
    threading.Thread(target=udp_server, args=(AUDIO_PORT, clients_audio, audio_lock, "AUDIO"), daemon=True).start()
    threading.Thread(target=udp_server, args=(SCREEN_PORT, clients_screen, screen_lock, "SCREEN"), daemon=True).start()

    print("Waiting for UDP servers to bind...")
    while not s_video or not s_audio or not s_screen: time.sleep(0.1)
    print("UDP servers bound.")

    print(f"[SERVER RUNNING] Bound to {SERVER_HOST}. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1.0) 
            now = time.time()
            timeout_threshold = 5 

            active_participants = {} 
            all_video_addrs_to_broadcast_to = set() 

            with video_lock, audio_lock, screen_lock, uuid_map_lock:

                def clean_and_gather(clients_dict, name):
                    inactive_addrs = [addr for addr, info in clients_dict.items() if now - info['last_seen'] > timeout_threshold]
                    for addr in inactive_addrs:
                        info = clients_dict.pop(addr, None) 
                        if info:
                            old_uuid = info.get('uuid')
                            print(f"[{name}] Removed inactive client: {addr} (UUID: {old_uuid})")
                            if old_uuid and old_uuid != 'unknown' and uuid_to_addr.get(old_uuid) == addr:
                                uuid_to_addr.pop(old_uuid, None)

                    for addr, info in clients_dict.items():
                        client_uuid = info.get('uuid')
                        if client_uuid and client_uuid != 'unknown':
                            username = info.get('username', 'Guest') 
                            active_participants[client_uuid] = username
                            if clients_dict is clients_video:
                                all_video_addrs_to_broadcast_to.add(addr)

                clean_and_gather(clients_video, "VIDEO")
                clean_and_gather(clients_audio, "AUDIO")
                clean_and_gather(clients_screen, "SCREEN")

            if all_video_addrs_to_broadcast_to and s_video:
                participant_pairs = [f"{uuid}:{username}" for uuid, username in active_participants.items()]
                payload_str = "||".join(participant_pairs)
                presence_packet = f"PRESENCE||{payload_str}".encode('utf-8')

                for addr_tuple in all_video_addrs_to_broadcast_to:
                    try:
                        s_video.sendto(presence_packet, addr_tuple)
                    except Exception as e: print(f"[PRESENCE BROADCAST ERROR to {addr_tuple}]: {e}")

    except KeyboardInterrupt: print("\n[SERVER STOPPING]... Goodbye.")
    except Exception as e: print(f"[MAIN THREAD ERROR] {e}")
    finally:
         print("Closing global sockets...")
         for sock in [s_video, s_audio, s_screen]:
             if sock:
                 try: sock.close()
                 except: pass

if __name__ == "__main__":
    main()