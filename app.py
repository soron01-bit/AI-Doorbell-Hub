import os
import uuid
import time
import threading
import queue
import wave
import struct
import json
import datetime
import numpy as np
import cv2
from flask import Flask, render_template, Response, request, jsonify, send_from_directory

import config
from face_engine import FaceEngine

# Import winsound on Windows for host-side bell ringing
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

app = Flask(__name__)

# Core system state
settings = config.load_settings()
settings["camera_enabled"] = False
engine = None
camera_source = settings.get("camera_source", "0")

# Threads & Lock
grabber_thread = None
processor_thread = None
system_running = True
camera_lock = threading.Lock()

# Global frames
raw_frame = None
processed_frame = None
frame_fps = 0.0

# Event notification system (SSE)
sse_clients = []
event_history = []
cooldowns = {}  # {name: timestamp}

# Ensure directory for sounds exists
os.makedirs(os.path.join(app.root_path, 'static', 'sounds'), exist_ok=True)
SOUND_FILE = os.path.join(app.root_path, 'static', 'sounds', 'dingdong.wav')

def generate_doorbell_sound(filepath):
    """Generates a beautiful synthetic 'ding-dong' doorbell sound file if it doesn't exist."""
    if os.path.exists(filepath):
        return
        
    sample_rate = 44100
    duration_ding = 1.0
    duration_dong = 1.5
    
    # Ding: 880Hz (A5), decays exponentially
    t_ding = np.linspace(0, duration_ding, int(sample_rate * duration_ding), False)
    val_ding = np.sin(2 * np.pi * 880 * t_ding) * np.exp(-3.5 * t_ding)
    
    # Dong: 659.25Hz (E5), decays exponentially
    t_dong = np.linspace(0, duration_dong, int(sample_rate * duration_dong), False)
    val_dong = np.sin(2 * np.pi * 659.25 * t_dong) * np.exp(-1.8 * t_dong)
    
    # Combine them (dong starts after 0.4 seconds)
    delay = 0.4
    delay_samples = int(sample_rate * delay)
    total_samples = delay_samples + len(val_dong)
    
    audio = np.zeros(total_samples)
    audio[:len(val_ding)] += val_ding * 0.6
    audio[delay_samples:delay_samples+len(val_dong)] += val_dong * 0.6
    
    # Normalize to avoid clipping
    audio = audio / np.max(np.abs(audio))
    # Convert to 16-bit PCM integers
    audio_int = (audio * 32767).astype(np.int16)
    
    # Write as WAV
    with wave.open(filepath, 'w') as f:
        f.setnchannels(1)  # Mono
        f.setsampwidth(2)  # 2 bytes per sample (16-bit)
        f.setframerate(sample_rate)
        # Write binary data
        for val in audio_int:
            f.writeframesraw(struct.pack('<h', val))
            
    print(f"Generated doorbell sound at {filepath}")

# Generate sound immediately
generate_doorbell_sound(SOUND_FILE)


# Video Grabber Thread
def run_frame_grabber():
    global raw_frame, system_running, camera_source
    print("Frame Grabber Thread Started")
    
    last_source = None
    cap = None
    
    while system_running:
        # Check if camera is disabled in settings
        if not settings.get("camera_enabled", True):
            if cap is not None:
                cap.release()
                cap = None
                last_source = None
                print("Camera disabled by user. Releasing device...")
            with camera_lock:
                raw_frame = None
            time.sleep(0.5)
            continue
            
        # Load current source safely
        with camera_lock:
            curr_source = camera_source
            
        # Parse source (integer if webcam index, string otherwise)
        if isinstance(curr_source, str) and curr_source.isdigit():
            curr_source = int(curr_source)
            
        # Check if source changed or camera not opened
        if curr_source != last_source or cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
                print("Releasing camera capture...")
            
            print(f"Opening camera source: {curr_source}")
            # Use DirectShow on Windows for webcam (makes opening much faster)
            if isinstance(curr_source, int):
                cap = cv2.VideoCapture(curr_source, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(curr_source)
                
            last_source = curr_source
            
            if not cap.isOpened():
                print(f"Failed to open camera source: {curr_source}. Retrying in 3 seconds...")
                time.sleep(3)
                continue
        
        # Read frame
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame from camera. Reconnecting...")
            cap.release()
            cap = None
            time.sleep(2)
            continue
            
        # Apply rotation
        rotation = settings.get("video_rotation", 0)
        if rotation == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
        with camera_lock:
            raw_frame = frame
            
        time.sleep(0.01) # brief sleep to yield execution

    if cap is not None:
        cap.release()
    print("Frame Grabber Thread Stopped")


# Play sound helper
def play_sound_host():
    """Plays doorbell sound on the host (laptop) machine."""
    if HAS_WINSOUND and settings.get("bell_enabled", True):
        try:
            # Play sound asynchronously
            winsound.PlaySound(SOUND_FILE, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            print(f"Host sound playback error: {e}")


# Trigger event helper
def trigger_doorbell_event(name, is_known, score=0.0):
    now = time.time()
    cooldown = settings.get("cooldown_period", 10.0)
    
    # Check cooldown for this person (or 'Unknown Visitor')
    if name in cooldowns and (now - cooldowns[name]) < cooldown:
        return
        
    cooldowns[name] = now
    
    event_time = datetime.datetime.now().strftime("%I:%M:%S %p")
    event = {
        "id": str(uuid.uuid4()),
        "time": event_time,
        "name": name,
        "type": "registered" if is_known else "unknown",
        "score": round(score, 3)
    }
    
    # Keep last 50 events
    event_history.insert(0, event)
    if len(event_history) > 50:
        event_history.pop()
        
    # Trigger host-side audio ONLY if the visitor is a registered member
    if is_known:
        play_sound_host()
    
    # Broadcast to SSE clients
    payload = json.dumps(event)
    for q in sse_clients:
        q.put(payload)
    print(f"Doorbell Event: {name} (Known: {is_known}, Score: {score:.3f})")


# Frame Processing Thread
def run_frame_processor():
    global raw_frame, processed_frame, frame_fps, system_running, engine
    print("Frame Processor Thread Started")
    
    # Load face engine inside thread to ensure OpenCV resources are thread-local
    try:
        engine = FaceEngine()
        print("Face Engine loaded successfully in processor thread.")
    except Exception as e:
        print(f"Failed to load Face Engine: {e}")
        return
        
    last_fps_time = time.time()
    frame_count = 0
    
    # Variables for presence tracking and inference caching
    presence_start = {}
    last_seen = {}
    last_faces = None
    last_matches = []
    
    while system_running:
        start_time = time.time()
        
        # Safely copy raw frame
        curr_frame = None
        with camera_lock:
            if raw_frame is not None:
                curr_frame = raw_frame.copy()
                
        if curr_frame is None:
            processed_frame = None
            time.sleep(0.05)
            continue
            
        annotated_frame = curr_frame.copy()
        
        # Run detection and recognition on every 2nd frame to boost FPS and keep stream buttery smooth
        if frame_count % 2 == 0 or last_faces is None:
            faces = engine.detect_faces(curr_frame)
            last_faces = faces
            last_matches = []
            
            if faces is not None:
                for face in faces:
                    embedding = engine.get_face_embedding(curr_frame, face)
                    name = "Unknown"
                    score = 0.0
                    is_known = False
                    
                    if embedding is not None:
                        thresh = settings.get("recognition_threshold", 0.363)
                        name, score = engine.match_face(embedding, threshold=thresh)
                        is_known = (name != "Unknown")
                        
                    last_matches.append((name, is_known, score))
        else:
            faces = last_faces
            
        detected_this_frame = set()
        
        if faces is not None:
            for idx, face in enumerate(faces):
                # Bounding box
                x, y, w, h = map(int, face[0:4])
                # Ensure box stays in image boundaries
                x = max(0, x)
                y = max(0, y)
                w = min(w, annotated_frame.shape[1] - x)
                h = min(h, annotated_frame.shape[0] - y)
                
                # Get match details for this face
                if idx < len(last_matches):
                    name, is_known, score = last_matches[idx]
                else:
                    name, is_known, score = "Unknown", False, 0.0
                
                # Update presence tracking
                detected_this_frame.add(name)
                if name not in presence_start:
                    presence_start[name] = start_time
                last_seen[name] = start_time
                
                # Calculate how long they've been standing here
                elapsed_presence = start_time - presence_start[name]
                delay = settings.get("detection_delay", 1.5)
                
                # Determine colors and label text (OpenCV uses BGR format)
                if is_known:
                    color = (113, 204, 46)  # Green in BGR
                    if elapsed_presence < delay:
                        text = f"{name} (Wait {delay - elapsed_presence:.1f}s)"
                    else:
                        text = f"{name} ({score:.2f})"
                else:
                    color = (60, 76, 231)  # Red in BGR
                    if elapsed_presence < delay:
                        text = f"Verifying... ({delay - elapsed_presence:.1f}s)"
                    else:
                        text = "Unknown Visitor"
                        
                # Draw bounding box
                cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), color, 2)
                
                # Draw label card background
                label_size, base_line = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                cv2.rectangle(annotated_frame, (x, y - label_size[1] - 10), (x + label_size[0] + 10, y), color, cv2.FILLED)
                
                # Draw label text
                cv2.putText(annotated_frame, text, (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
                
                # Trigger doorbell event ONLY if they stayed for >= delay seconds
                if elapsed_presence >= delay:
                    trigger_doorbell_event(name, is_known, score)
                    
        # Clean up presence tracking for people who have walked away (not seen for > 1.0s)
        for name in list(presence_start.keys()):
            if name not in detected_this_frame:
                if start_time - last_seen.get(name, 0) > 1.0:
                    presence_start.pop(name, None)
                    last_seen.pop(name, None)
                    
        # Calculate processing FPS
        frame_count += 1
        curr_time = time.time()
        elapsed = curr_time - last_fps_time
        if elapsed >= 1.0:
            frame_fps = frame_count / elapsed
            frame_count = 0
            last_fps_time = curr_time
            
        # Draw status info on frame
        fps_text = f"FPS: {frame_fps:.1f}"
        cv2.putText(annotated_frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
        
        # Store annotated frame
        processed_frame = annotated_frame
        
        # Sleep slightly to match camera FPS and avoid burning CPU
        elapsed_processing = time.time() - start_time
        sleep_time = max(0.001, 0.033 - elapsed_processing) # target ~30fps max
        time.sleep(sleep_time)
        
    print("Frame Processor Thread Stopped")


# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')


# Video Stream Endpoint
def gen_video():
    global processed_frame, system_running
    while system_running:
        if processed_frame is not None:
            # Encode frame to JPEG
            ret, jpeg = cv2.imencode('.jpg', processed_frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
        time.sleep(0.04)  # stream at ~25fps


@app.route('/video_feed')
def video_feed():
    return Response(gen_video(), mimetype='multipart/x-mixed-replace; boundary=frame')


# SSE Live Notification endpoint
@app.route('/api/events')
def events():
    def event_stream():
        q = queue.Queue()
        sse_clients.append(q)
        try:
            # Send initial message to establish connection
            yield f"data: {json.dumps({'type': 'init'})}\n\n"
            while True:
                data = q.get()
                yield f"data: {data}\n\n"
        except GeneratorExit:
            pass
        finally:
            sse_clients.remove(q)
            
    return Response(event_stream(), mimetype='text/event-stream')


# Settings endpoints
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    global camera_source, settings
    if request.method == 'GET':
        resp = settings.copy()
        resp["camera_active"] = (raw_frame is not None)
        resp["fps"] = round(frame_fps, 1)
        return jsonify(resp)
        
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
        
    # Update settings
    source = data.get("camera_source", settings["camera_source"])
    if isinstance(source, str) and (source.startswith("http://") or source.startswith("https://")):
        from urllib.parse import urlparse
        parsed = urlparse(source)
        if parsed.netloc and (not parsed.path or parsed.path == "/"):
            source = f"{parsed.scheme}://{parsed.netloc}/video"
            
    settings["camera_source"] = source
    settings["recognition_threshold"] = float(data.get("recognition_threshold", settings["recognition_threshold"]))
    settings["bell_enabled"] = bool(data.get("bell_enabled", settings.get("bell_enabled", True)))
    settings["cooldown_period"] = float(data.get("cooldown_period", settings.get("cooldown_period", 10.0)))
    settings["camera_enabled"] = bool(data.get("camera_enabled", settings.get("camera_enabled", True)))
    settings["video_rotation"] = int(data.get("video_rotation", settings.get("video_rotation", 0)))
    settings["detection_delay"] = float(data.get("detection_delay", settings.get("detection_delay", 1.5)))
    
    config.save_settings(settings)
    
    # Update active camera source
    with camera_lock:
        camera_source = settings["camera_source"]
        
    return jsonify({"success": True, "settings": settings})


# Faces endpoints
@app.route('/api/faces', methods=['GET'])
def get_faces():
    if engine is None:
        return jsonify([])
    return jsonify(engine.get_registered_faces())


@app.route('/api/faces/upload', methods=['POST'])
def upload_face():
    if engine is None:
        return jsonify({"success": False, "message": "Face engine not initialized."}), 500
        
    name = request.form.get("name")
    if not name:
        return jsonify({"success": False, "message": "Name is required"}), 400
        
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "No file selected"}), 400
        
    try:
        # Read file to numpy array
        file_bytes = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({"success": False, "message": "Invalid image format"}), 400
            
        result = engine.register_face_from_image(name, img)
        return jsonify({"success": True, "face": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route('/api/faces/capture', methods=['POST'])
def capture_face():
    global raw_frame, engine
    if engine is None:
        return jsonify({"success": False, "message": "Face engine not initialized."}), 500
        
    name = request.json.get("name") if request.json else None
    if not name:
        return jsonify({"success": False, "message": "Name is required"}), 400
        
    # Safely get current raw frame
    curr_frame = None
    with camera_lock:
        if raw_frame is not None:
            curr_frame = raw_frame.copy()
            
    if curr_frame is None:
        return jsonify({"success": False, "message": "No frame available from camera stream"}), 400
        
    try:
        # Register face from raw frame
        result = engine.register_face_from_image(name, curr_frame)
        return jsonify({"success": True, "face": result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route('/api/faces/<face_id>', methods=['DELETE'])
def delete_face(face_id):
    if engine is None:
        return jsonify({"success": False, "message": "Face engine not initialized."}), 500
        
    success = engine.delete_face(face_id)
    if success:
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Face ID not found"}), 404


@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify(event_history)


@app.route('/api/trigger_bell', methods=['POST'])
def trigger_bell():
    play_sound_host()
    
    # Broadcast to SSE clients to ring on browser too
    event_time = datetime.datetime.now().strftime("%I:%M:%S %p")
    event = {
        "id": str(uuid.uuid4()),
        "time": event_time,
        "name": "Manual Bell Button",
        "type": "manual",
        "score": 1.0
    }
    
    payload = json.dumps(event)
    for q in sse_clients:
        q.put(payload)
        
    return jsonify({"success": True})


# Cleanup
def cleanup():
    global system_running, grabber_thread, processor_thread
    system_running = False
    if grabber_thread is not None:
        grabber_thread.join(timeout=2.0)
    if processor_thread is not None:
        processor_thread.join(timeout=2.0)


if __name__ == '__main__':
    # Start threads
    grabber_thread = threading.Thread(target=run_frame_grabber, daemon=True)
    grabber_thread.start()
    
    processor_thread = threading.Thread(target=run_frame_processor, daemon=True)
    processor_thread.start()
    
    try:
        # Run Flask server
        # Host '0.0.0.0' allows other devices in the same network (e.g. your phone) to connect
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    finally:
        cleanup()
