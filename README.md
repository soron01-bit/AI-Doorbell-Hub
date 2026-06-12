# AI-Doorbell-Hub

# 🔔 AI CCTV Smart Doorbell System

A premium, modern, and high-performance smart doorbell system featuring real-time face detection, recognition, visitor categorization, and dynamic presence delay triggers. Built with a gorgeous glassmorphism Day-Mode UI, it runs at up to 30 FPS.

---

## ✨ Key Features

*   **Buttery Smooth 30 FPS Live Stream**: Powered by gated inference (running neural network detection on alternate frames) and optimized thread sleeping to keep video streams extremely smooth and CPU usage low.
*   **Customizable Presence Delay**: Prevent false alarms or quick walk-bys. Set a threshold (e.g., 1.5s) in the settings. The visitor must stand in front of the camera for that duration before triggering actions.
*   **Smart Categorization & Doorbell Gate**:
    *   **Registered Members**: Visualized in **Green** with countdown indicators. Once the presence delay is met, the system plays a doorbell chime (host speaker + web audio).
    *   **Unknown Visitors**: Visualized in **Red** with verification timers. Once the delay is met, they are logged silently in the Activity Timeline without ringing the bell.
*   **Smart IP Camera Correction**: Connect USB webcams or mobile IP cameras (IP Webcam app). The backend auto-resolves bare IP addresses to raw MJPEG streams.
*   **Dynamic Aspect Ratio & Rotation**: Support for `90°`, `180°`, and `270°` rotation. Rotations to portrait automatically adjust the website video player aspect ratio to 3:4.
*   **High-Accuracy YuNet & SFace**: Employs state-of-the-art OpenCV YuNet for face detection and SFace for recognition, optimized to detect faces at angles or with glasses.
*   **Safe Camera Startup**: The camera is disabled on server launch and activates only when the administrator explicitly clicks **"Start System & Camera"**.

---

## 🛠️ Tech Stack

*   **Backend**: Python, Flask, OpenCV (YuNet Detection, SFace Recognition)
*   **Frontend**: Vanilla HTML5, CSS3 (Modern Glassmorphic Day-Mode theme, CSS variables, CSS transitions), Javascript (ES6, Server-Sent Events for real-time logs)
*   **Database/Storage**: Local JSON files (`settings.json`, `faces.json`) and disk-based image alignment storage.

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure you have Python 3.8+ installed on your system.

### 2. Install Dependencies
Clone the repository and install the required packages:
```bash
pip install -r requirements.txt
