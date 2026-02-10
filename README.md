# **CIDER: LAN Collaboration Suite**

**CIDER** is a robust, standalone communication suite engineered for secure, multi-user collaboration within isolated Local Area Networks (LANs). Designed for environments where internet access is restricted, unreliable, or intentionally disabled—such as high-security offices, research labs, or emergency response centers—CIDER provides a comprehensive set of real-time tools without relying on external servers or cloud infrastructure.

By leveraging a centralized client-server architecture and a hybrid TCP/UDP protocol stack, CIDER delivers low-latency performance for media streams while ensuring data integrity for critical communications.

## 🚀 Quick Start


Get CIDER running on your Local Area Network in just a few minutes.

### ✅ Prerequisites

* Python 3.x installed on all machines
* All devices connected to the same LAN
* Firewall configured to allow required ports

---

### 🖥️ Step 1 — Start the Server

On the host machine:

```bash
python server.py
```

✔️ The server will begin listening on the required ports.

---

### 💻 Step 2 — Launch the Client

On each participant machine:

```bash
python client.py
```

---

### 🔑 Step 3 — Enter Login Details

* **Username:** Choose a unique display name
* **Server IP:**

  * Use `127.0.0.1` for local testing
  * Use the host machine’s IPv4 address for LAN sessions

---

### 🔗 Step 4 — Connect to the Session

Click **CONNECT** to join the collaboration suite.

✔️ You should now see active participants and available features.

---

### 🎥 Step 5 — Start Collaborating

You can immediately:

* Join video/audio calls
* Share your screen
* Send chat messages
* Transfer files

✅ Your LAN collaboration environment is now live!


### **Core Modules**

* **Low-Latency Video Conferencing:** Real-time multi-user video grid powered by UDP broadcasting.  
* **Real-Time Audio Conferencing:** Decentralized audio mixing for seamless voice communication.  
* **High-FPS Screen Sharing:** Optimized for presentations with a dedicated "Presenter Mode" layout.  
* **Comprehensive Chat System:** Reliable TCP-based messaging supporting both public groups and private, direct communication.  
* **Secure File Sharing:** Transactional file transfer system with progress tracking and automatic distribution notifications.

To run CIDER, ensure your environment meets the following requirements:

* All devices must be connected to the same Local Area Network (LAN).

## **Usage Instructions**

### **1\. Deploying the Server**

The server acts as the central relay and session manager. It must be running on a designated host machine within the LAN before any clients can connect.

1. Open a terminal or command prompt on the host machine.  
2. Navigate to the project directory.  
3. Launch the server:  
   python server.py  
4. **Verification:** The console will display a startup message confirming that it is listening on all required ports (9993 through 9999).  
   * *Note:* If prompted by your operating system, allow Python to communicate on both Private and Public networks via the Firewall.

### **2\. Connecting Clients**

Users on any computer within the LAN (including the host machine) can connect to the session.

1. Open a terminal on the client machine.  
2. Launch the client application:  
   python client.py  
3. **Login Configuration:**  

![cider_login_page](https://github.com/user-attachments/assets/b8ae0313-424a-4d99-a339-bff33ca4bfd0)


   * **Username:** Enter a unique display name (e.g., "Alice", "Admin"). This name will be visible to all participants.  
   * **IP Address:** Enter the **IPv4 Address** of the machine running server.py.  
     * *Local Testing:* Use 127.0.0.1.  
     * *LAN Connection:* Find the server's IP by running ipconfig (Windows) or ifconfig (Linux/Mac) on the server machine.  
5. Click the **CONNECT** button to join the session.

## **Features and Interface Overview**

The CIDER interface is designed for simplicity and efficiency, consolidated into a single window.

### **Video and Audio Conferencing**

<img width="1379" height="775" alt="main_application" src="https://github.com/user-attachments/assets/5e5476a8-83ac-4444-a9c3-43af8829ba85" />


* **Dynamic Grid View:** The application automatically arranges video feeds from all active participants into an optimal grid layout (2x2, 3x3, etc.).  
* **Media Controls:**  
  * **Microphone:** Toggle your audio stream using the dedicated control button.  
  * **Camera:** Toggle your video stream using the dedicated control button.  
  * **Status Indicators:** If a user turns off their camera or microphone, their feed will update with a status icon to inform other participants.

### **Screen Sharing and Presentation**

<img width="1379" height="775" alt="screen_share" src="https://github.com/user-attachments/assets/419eea09-190d-4a4f-8979-60ed34ad1f22" />


* **Start Presenting:** Click the Present button to instantly share your primary screen with the group.  
* **Presenter Mode:** When a presentation starts, the layout automatically shifts. The screen share takes priority, occupying **70% of the window**, while participant video feeds are resized and moved to a vertical thumbnail strip on the right (30% width).  
* **Exclusivity:** To prevent conflicts, only one user can present at a time.

### **Advanced Chat System**

<img width="1379" height="775" alt="chat" src="https://github.com/user-attachments/assets/a98f02b4-a8f1-482d-9f64-4d9f965cbcf0" />

Access the chat panel by clicking the **"Chat"** toggle button.

* **Group Chat:** By default, messages typed in the input box are broadcast to all connected users.  
* **Private Messaging:**  
  1. Open the **"Participants"** panel to see a live list of online users.  
  2. Click on a specific user's name.  
  3. The chat context switches to **Private Mode**, indicated by a To: \[User\] banner above the input box.  
  4. Messages sent in this mode are routed exclusively to the selected recipient.  
  5. To return to the main group chat, click the close button on the target banner.  
* **Smart Notifications:** If you receive a message while the chat panel is closed, the button label will update to alert you.

### 

### **File Sharing**

<img width="940" height="529" alt="image" src="https://github.com/user-attachments/assets/0c18dc64-ce4d-4aa8-83d0-29a73dccd348" />

<img width="1379" height="775" alt="File_sharing" src="https://github.com/user-attachments/assets/9b457835-1eae-48a9-88a8-48791ab3c4a5" />

Access the file transfer hub by clicking the **"Files"** button.

* **Upload:** Click "Upload" to select a file from your computer. CIDER supports large file transfers (up to 10GB). A real-time progress bar will track the upload status.  
* **Distribution:** Once an upload is complete, the server automatically broadcasts the file's availability to all clients.  
* **Download:** The file list updates automatically. Double-click any file entry to download it directly to your Downloads/CollabSuite directory.

### **Feedback and Logging**

<img width="940" height="524" alt="image" src="https://github.com/user-attachments/assets/8f032534-0711-4f9a-95f2-00c12b5f2221" />


* Click the **"Feedback"** button to report bugs or submit suggestions.  
* All submissions are timestamped and logged to a secure CSV file (cider\_feedback.csv) on the server for administrator review.

## **Troubleshooting Guide**

### **Common Issues**

**1\. "Connection Failed" or Timeouts**

* **Firewall Block:** This is the most common issue. Ensure the machine running server.py allows incoming connections on ports 9993-9999. You may need to create an exception in Windows Defender Firewall.  
* **Incorrect IP:** Verify that the IP address entered in the client login screen matches the server's actual LAN IPv4 address.

**2\. Video Lag or Stuttering**

* **Network Congestion:** CIDER uses high-bandwidth UDP streams. Ensure your Wi-Fi signal is strong, or switch to a wired Ethernet connection for optimal performance.  
* **Packet Loss:** If video frames appear corrupted ("glitchy"), this is a symptom of UDP packet loss on the network.

**3\. "Disconnected" Notification**

* **Timeout Protection:** The server employs a "watchdog" timer. If a client crashes or loses network connectivity, the server will automatically remove them from the session after 5 seconds of inactivity.  
* **Manual Disconnect:** Clicking the **"Hang Up"** button sends an explicit disconnect signal, removing you from the session immediately.

## **Technical Architecture**

CIDER is built on a pure Python stack, utilizing raw sockets for maximum control over network traffic.

### **Port Allocation Map**

The system uses distinct ports for each service to prevent congestion and ensure stability.

| Port | Protocol | Service | Description |
| :---- | :---- | :---- | :---- |
| **9999** | UDP | Video Stream | Real-time MJPEG video broadcasting |
| **9998** | UDP | Audio Stream | Low-latency PCM audio relay |
| **9997** | TCP | Chat System | Reliable message routing (Public/Private) |
| **9996** | TCP | File Control | Persistent connection for file list sync |
| **9995** | UDP | Screen Share | High-FPS screen capture stream |
| **9994** | TCP | Feedback | Logging service for user reports |
| **9993** | TCP | File Data | Transactional socket for file transfers |

### **Key Technologies**

* **GUI Framework:** tkinter (Python Standard Library) – For a lightweight, cross-platform native interface.  
* **Computer Vision:** OpenCV (cv2) – For efficient webcam capture and image resizing/compression.  
* **Image Processing:** Pillow (PIL) – For rendering video frames onto the GUI.  
* **Audio Processing:** PyAudio – For capturing and playing back raw PCM audio streams.  
* **Screen Capture:** mss – For high-performance, cross-platform screen grabbing.  
* **Networking:** Standard Python socket & threading libraries – For managing concurrent TCP/UDP connections.

## **Implementation Details**

### **Server Implementation**

The server is implemented using Python's socket and threading modules to achieve maximum concurrency for a LAN environment.

#### **Core Configuration and State Management**

All global state variables, including client lists and locks, are defined at the top of the script.

#### 

#### 


#### **Client Tracking**

* **TCP Lists:** Lists of active TCP socket objects, protected by specific locks.  
* **UDP Dictionaries:** Dictionaries mapping IP/Port tuples to client metadata (uuid, last\_seen, username). This allows the server to track multiple UDP streams from a single client.  
* **File List:** Maps the user-visible file display name to the unique, safe filename stored on disk.

#### **Synchronization Primitives**

The server heavily relies on threading locks to protect shared resources, ensuring thread safety across all concurrent operations.

#### **TCP Server Handlers**

TCP connections are persistent (Chat, File Control) or transactional (File Data, Feedback).

* **Chat Server:** Handles registration and broadcasts messages via a helper function. It also manages graceful disconnects by broadcasting user exit events.  
* **File Control Server:** Sends the initial file list and maintains a persistent connection for file added broadcasts.  
* **File Data Server:** Handles single uploads (saving files securely using unique identifiers to avoid collisions) and downloads (streaming files from disk).  
* **Feedback Server:** Receives length-prefixed TCP packets and appends feedback to a CSV file.

#### **UDP Server Handlers**

A single, multi-purpose UDP server function is reused for all three UDP services (Video, Audio, Screen) by accepting the port, client dictionary, and lock as arguments.

* **Control Messages:** It processes registration and keep-alive packets to manage client state and stream status.  
* **Media Relay:** For media data, it verifies the packet type, extracts the sender's identifier, and calls a broadcast function to relay the data to all other clients for that service.

#### **Session Management and Cleanup**

The main server loop runs continuous session checks.

* **Timeout Cleanup:** Every 1.0 second, the loop iterates through the UDP client dictionaries, removing any client whose last seen timestamp exceeds the timeout threshold. This gracefully handles clients that crash or lose connection.  
* **Presence Broadcast:** The server compiles a list of all active identifiers and usernames from all UDP clients and broadcasts a presence packet. This is the source for the client GUI to determine who is currently online.

### 

### **Client Implementation**

The client application is built using the tkinter library for the GUI, managing all media I/O and concurrent network operations.

#### **User Interface Design**

The GUI is designed for a single-window experience, organized into a Status Bar, a Main Content Area (Video/Screen Grid), a Control Bar, and a Dynamic Side Panel.

#### **Client Concurrency and Threading**

The client relies on a multi-threaded approach to keep the UI responsive while handling blocking network and I/O operations.

* **UI Thread:** Handles all UI updates. All network-related UI updates are scheduled to ensure thread safety.  
* **Media Capture Threads:** Separate threads run continuous loops for video, audio, and screen capture and transmission.  
* **Media Receive Threads:** Dedicated threads listen continuously on their respective UDP sockets for incoming media streams.  
* **Control Threads:** Persistent listeners for TCP services (chat, file control) and a periodic keep-alive thread.

#### **Media I/O and Processing**

* **Video and Screen Capture:** OpenCV is used for webcam capture. mss is used for efficient screen capture. Captured frames are downscaled and encoded into JPEG format before being sent via UDP to minimize bandwidth and latency.  
* **Audio I/O:** The pyaudio library manages low-level microphone input and speaker output streams. Audio mixing is handled implicitly by the server relay mechanism.

#### **Stream Management and Timeout**

The client implements local state management to handle stream drop-outs and UI updates. A timeout checker runs periodically to reset video labels if packets stop arriving.

## **Performance Analysis**

### **Performance Considerations**

The design choices were heavily influenced by the need to balance low-latency media with resource management in a LAN setting.

* **Latency Management:** The choice of UDP inherently minimizes latency by eliminating TCP's handshaking and retransmission overhead. The server acts purely as a non-blocking relay for media packets.  
* **Bandwidth Optimization:** Using JPEG compression for video and screen sharing dramatically reduces the bandwidth required per stream. Large chunk sizes are used for file transfers to minimize per-packet overhead.

### **Limitations and Future Work**

While functional, the application can be improved with the following enhancements:

* **Server-Side Audio Mixing:** Implementing a true audio mixer on the server could improve audio quality by ensuring consistent playback volumes and reducing potential echo issues.  
* **Screen Sharing Protocol:** Changing the screen sharing protocol from UDP to TCP could be considered for better reliability.  
* **Adaptive Bitrate:** Implementing logic to dynamically adjust the JPEG compression quality based on network congestion would optimize performance under load.  
* **Authentication:** The current system relies on self-reported usernames. Future work could include a simple token-based authentication system.

## 🤝 Contributions



### 👨‍💻 Bhargav Sai 
- Designed and implemented the **core client–server architecture**, including protocol mapping and multi-port communication strategy.
- Developed the **multi-threaded UDP media relay system** for video, audio, and screen sharing.
- Implemented **real-time video conferencing**, covering webcam capture, JPEG compression, UDP streaming, and client-side rendering.
- Designed and coded the **dynamic video grid algorithm**, including automatic layout adjustment and **Presenter Mode (70/30 split)**.
- Implemented **stream timeout detection** and recovery to handle dropped or inactive media streams gracefully.
- Authored major documentation sections related to **System Architecture** and **Media Module Implementation**. :contentReference[oaicite:0]{index=0}

---

### 👨‍💻 Vivek Vardhan
- Designed and implemented **TCP-based communication protocols** for chat, file sharing, and feedback services.
- Developed the complete **GUI using Tkinter**, including Login Screen, Control Bar, Dynamic Side Panel, and UI styling.
- Implemented the **Group Text Chat system** with reliable message delivery, system notifications, and user presence updates.
- Built the **File Sharing module**, including transactional upload/download handling, progress tracking, and file availability broadcasts.
- Implemented **UDP keep-alive, timeout cleanup, and resource deallocation logic** to ensure robustness against crashes and disconnects.
- Authored documentation covering **Communication Protocols, Server & Client Implementation, Performance Analysis, and Future Work**. 
