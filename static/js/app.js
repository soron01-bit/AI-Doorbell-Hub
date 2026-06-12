// State Variables
let systemInitialized = false;
let cameraEnabled = true;

// DOM Elements
const audioOverlay = document.getElementById('audio-overlay');
const btnInitialize = document.getElementById('btn-initialize');
const bellSound = document.getElementById('bell-sound');
const btnManualBell = document.getElementById('btn-manual-bell');
const btnToggleCamera = document.getElementById('btn-toggle-camera');
const btnToggleCameraText = document.getElementById('btn-toggle-camera-text');

// Status Elements
const statusText = document.getElementById('status-text');
const statusBadge = document.querySelector('.status-badge');

// Forms & Config Elements
const formSettings = document.getElementById('form-settings');
const cameraSourceInput = document.getElementById('camera-source');
const cameraPresetSelect = document.getElementById('camera-preset');
const thresholdInput = document.getElementById('threshold');
const thresholdVal = document.getElementById('threshold-val');
const cooldownInput = document.getElementById('cooldown');
const bellEnabledCheckbox = document.getElementById('bell-enabled');
const videoRotationSelect = document.getElementById('video-rotation');
const detectionDelayInput = document.getElementById('detection-delay');

// Tabs & Registration Elements
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const formRegCapture = document.getElementById('form-register-capture');
const formRegUpload = document.getElementById('form-register-upload');
const regNameCap = document.getElementById('reg-name-cap');
const regNameUp = document.getElementById('reg-name-up');
const regFile = document.getElementById('reg-file');
const fileUploadLabel = document.querySelector('.file-upload-label');

// Gallery & Log Lists
const membersList = document.getElementById('members-list');
const memberCount = document.getElementById('member-count');
const logsContainer = document.getElementById('logs-container');
const btnClearLogs = document.getElementById('btn-clear-logs');
const videoFeed = document.getElementById('video-feed');
const videoPlaceholder = document.getElementById('video-placeholder');
const videoContainer = document.querySelector('.video-container');

// Initialize Autoplay Action and Start Camera System
btnInitialize.addEventListener('click', () => {
    // 1. Play sound once to unlock browser audio restrictions
    bellSound.volume = 0.5;
    bellSound.play().then(() => {
        bellSound.pause();
        bellSound.currentTime = 0;
    }).catch(e => console.log("Audio unlock failed: ", e));

    // 2. Hide overlay
    audioOverlay.classList.remove('active');
    systemInitialized = true;

    // 3. Post to API to turn on the camera system
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_enabled: true })
    })
    .then(res => res.json())
    .then(result => {
        // 4. Run dashboard initialization
        startDashboard();
    })
    .catch(err => {
        console.error("Failed to auto-enable camera on startup:", err);
        startDashboard();
    });
});

// Tab Navigation
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        btn.classList.add('active');
        const activeTabId = btn.getAttribute('data-tab');
        document.getElementById(activeTabId).classList.add('active');
    });
});

// Preset Select Handler
cameraPresetSelect.addEventListener('change', () => {
    const val = cameraPresetSelect.value;
    if (val !== 'ip') {
        cameraSourceInput.value = val;
    } else {
        cameraSourceInput.value = '';
        cameraSourceInput.focus();
    }
});

// Threshold Slider Handler
thresholdInput.addEventListener('input', () => {
    thresholdVal.textContent = thresholdInput.value;
});

// Custom File Input Label
regFile.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        fileUploadLabel.textContent = e.target.files[0].name;
    } else {
        fileUploadLabel.textContent = 'Browse Files...';
    }
});

// Toggle Camera Feed (Stop / Start)
btnToggleCamera.addEventListener('click', () => {
    const nextState = !cameraEnabled;
    
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_enabled: nextState })
    })
    .then(res => res.json())
    .then(result => {
        if (result.success) {
            cameraEnabled = nextState;
            updateToggleButtonUI(cameraEnabled);
            updateStatus();
        }
    })
    .catch(err => console.error("Failed to toggle camera:", err));
});

function updateToggleButtonUI(isEnabled) {
    if (isEnabled) {
        btnToggleCamera.classList.remove('stopped');
        btnToggleCameraText.textContent = "Stop Camera Feed";
        btnToggleCamera.querySelector('svg').innerHTML = `
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <rect x="9" y="9" width="6" height="6"/>
        `;
    } else {
        btnToggleCamera.classList.add('stopped');
        btnToggleCameraText.textContent = "Start Camera Feed";
        btnToggleCamera.querySelector('svg').innerHTML = `
            <polygon points="5 3 19 12 5 21 5 3"/>
        `;
    }
}

// Manual Bell Test
btnManualBell.addEventListener('click', () => {
    fetch('/api/trigger_bell', { method: 'POST' })
        .then(res => res.json())
        .catch(err => console.error("Error triggering bell manually:", err));
});

// Clear local events list display
btnClearLogs.addEventListener('click', () => {
    logsContainer.innerHTML = `
        <div class="empty-state">
            <p>Logs cleared. Waiting for events...</p>
        </div>
    `;
});

// Core Startup Logic
function startDashboard() {
    loadSettings();
    loadFaces();
    loadLogs();
    setupSSE();
    
    // Status loop every 3 seconds
    setInterval(updateStatus, 3000);
}

// Fetch settings from API
function loadSettings() {
    fetch('/api/settings')
        .then(res => res.json())
        .then(data => {
            cameraSourceInput.value = data.camera_source;
            thresholdInput.value = data.recognition_threshold;
            thresholdVal.textContent = data.recognition_threshold;
            cooldownInput.value = data.cooldown_period;
            bellEnabledCheckbox.checked = data.bell_enabled;
            videoRotationSelect.value = data.video_rotation || 0;
            detectionDelayInput.value = data.detection_delay !== undefined ? data.detection_delay : 1.5;
            
            const rot = parseInt(data.video_rotation || 0);
            if (rot === 90 || rot === 270) {
                videoContainer.classList.add('portrait-mode');
            } else {
                videoContainer.classList.remove('portrait-mode');
            }

            // Set preset dropdown accordingly
            if (data.camera_source === '0' || data.camera_source === '1') {
                cameraPresetSelect.value = data.camera_source;
            } else {
                cameraPresetSelect.value = 'ip';
            }
            
            cameraEnabled = data.camera_enabled;
            updateToggleButtonUI(cameraEnabled);
            updateConnectionUI(data.camera_active, data.fps);
        })
        .catch(err => console.error("Failed to load settings:", err));
}

// Update connections and FPS dynamically
function updateStatus() {
    fetch('/api/settings')
        .then(res => res.json())
        .then(data => {
            updateConnectionUI(data.camera_active, data.fps);
        })
        .catch(err => {
            console.error("Status check failed:", err);
            updateConnectionUI(false, 0);
        });
}

function updateConnectionUI(isActive, fps) {
    if (isActive) {
        statusText.textContent = `Connected (${fps} FPS)`;
        statusBadge.classList.remove('disconnected');
        videoFeed.classList.remove('hidden');
        videoPlaceholder.classList.add('hidden');
        
        // Ensure image source is active
        if (!videoFeed.src.includes('/video_feed')) {
            videoFeed.src = '/video_feed';
        }
    } else {
        statusText.textContent = 'Disconnected';
        statusBadge.classList.add('disconnected');
        videoFeed.classList.add('hidden');
        videoPlaceholder.classList.remove('hidden');
        // Stop fetching video stream to avoid spamming errors
        videoFeed.src = '';
    }
}

// Save Settings Form
formSettings.addEventListener('submit', (e) => {
    e.preventDefault();
    
    const data = {
        camera_source: cameraSourceInput.value,
        recognition_threshold: parseFloat(thresholdInput.value),
        cooldown_period: parseFloat(cooldownInput.value),
        bell_enabled: bellEnabledCheckbox.checked,
        video_rotation: parseInt(videoRotationSelect.value),
        detection_delay: parseFloat(detectionDelayInput.value)
    };
    
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(result => {
        if (result.success) {
            alert("Settings updated successfully! Restarting camera feed...");
            loadSettings();
        } else {
            alert("Error: " + result.message);
        }
    })
    .catch(err => console.error("Failed to save settings:", err));
});

// Load Registered Faces
function loadFaces() {
    fetch('/api/faces')
        .then(res => res.json())
        .then(faces => {
            memberCount.textContent = faces.length;
            
            if (faces.length === 0) {
                membersList.innerHTML = `
                    <div class="empty-state">
                        <p>No family members registered yet.</p>
                    </div>
                `;
                return;
            }
            
            membersList.innerHTML = faces.map(face => `
                <div class="member-card" data-id="${face.id}">
                    <button class="btn-delete-face" onclick="deleteFace('${face.id}')" title="Delete Member">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                    <img class="member-avatar" src="${face.image_url}?t=${Date.now()}" alt="${face.name}">
                    <div class="member-name">${escapeHTML(face.name)}</div>
                </div>
            `).join('');
        })
        .catch(err => console.error("Failed to load faces:", err));
}

// Delete Face
function deleteFace(id) {
    if (!confirm("Are you sure you want to delete this family member?")) return;
    
    fetch(`/api/faces/${id}`, { method: 'DELETE' })
        .then(res => res.json())
        .then(result => {
            if (result.success) {
                loadFaces();
            } else {
                alert("Error deleting face: " + result.message);
            }
        })
        .catch(err => console.error("Failed to delete face:", err));
}

// Register Face: Capture Live from Stream
formRegCapture.addEventListener('submit', (e) => {
    e.preventDefault();
    const name = regNameCap.value.trim();
    if (!name) return;
    
    const btnSubmit = formRegCapture.querySelector('button[type="submit"]');
    const origText = btnSubmit.innerHTML;
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Capturing Face...";
    
    fetch('/api/faces/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    })
    .then(res => res.json())
    .then(result => {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = origText;
        
        if (result.success) {
            alert(`Successfully registered ${name}!`);
            regNameCap.value = '';
            loadFaces();
        } else {
            alert("Failed to register: " + result.message);
        }
    })
    .catch(err => {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = origText;
        console.error("Capture registration error:", err);
        alert("Server error occurred while capturing face.");
    });
});

// Register Face: Upload File
formRegUpload.addEventListener('submit', (e) => {
    e.preventDefault();
    const name = regNameUp.value.trim();
    const file = regFile.files[0];
    
    if (!name || !file) {
        alert("Please enter a name and select a photo.");
        return;
    }
    
    const btnSubmit = formRegUpload.querySelector('button[type="submit"]');
    const origText = btnSubmit.innerHTML;
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Uploading & Processing...";
    
    const formData = new FormData();
    formData.append("name", name);
    formData.append("file", file);
    
    fetch('/api/faces/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(result => {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = origText;
        
        if (result.success) {
            alert(`Successfully uploaded and registered ${name}!`);
            regNameUp.value = '';
            regFile.value = '';
            fileUploadLabel.textContent = 'Browse Files...';
            loadFaces();
        } else {
            alert("Failed to register: " + result.message);
        }
    })
    .catch(err => {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = origText;
        console.error("Upload registration error:", err);
        alert("Server error occurred during upload.");
    });
});

// Load Event Logs
function loadLogs() {
    fetch('/api/logs')
        .then(res => res.json())
        .then(logs => {
            renderLogs(logs);
        })
        .catch(err => console.error("Failed to load logs:", err));
}

function renderLogs(logs) {
    if (logs.length === 0) {
        logsContainer.innerHTML = `
            <div class="empty-state">
                <p>No activity recorded yet.</p>
            </div>
        `;
        return;
    }
    
    logsContainer.innerHTML = logs.map(log => `
        <div class="log-item ${log.type}">
            <div class="log-icon-wrapper">
                ${getLogIcon(log.type)}
            </div>
            <div class="log-details">
                <div class="log-message">${getLogMessage(log)}</div>
                <div class="log-time">${log.time}</div>
            </div>
            ${log.score > 0 ? `<div class="log-score">Score: ${log.score}</div>` : ''}
        </div>
    `).join('');
}

function getLogIcon(type) {
    if (type === 'registered') {
        return `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
        `;
    } else if (type === 'unknown') {
        return `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
        `;
    } else {
        return `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 8v4M12 16h.01"/>
            </svg>
        `;
    }
}

function getLogMessage(log) {
    if (log.type === 'registered') {
        return `Detected family member: <strong>${escapeHTML(log.name)}</strong>`;
    } else if (log.type === 'unknown') {
        return `<span style="color:var(--danger)">Unregistered visitor detected at the door</span>`;
    } else if (log.type === 'manual') {
        return `Doorbell manual chime test triggered`;
    }
    return `Doorbell event triggered`;
}

// Setup SSE Listener for Live Chimes
function setupSSE() {
    const sse = new EventSource('/api/events');
    
    sse.onmessage = function(e) {
        const data = JSON.parse(e.data);
        if (data.type === 'init') return;
        
        // Add log immediately to list
        loadLogs();
        
        // Trigger browser bell chime if bell_enabled and it's a registered member
        if (bellEnabledCheckbox.checked && data.type === "registered") {
            playChimeEffect();
        }
    };
    
    sse.onerror = function() {
        console.warn("SSE connection closed. Reconnecting...");
        setTimeout(setupSSE, 5000);
    };
}

// Play Sound and Vibrate Bell Icon
function playChimeEffect() {
    bellSound.currentTime = 0;
    bellSound.play().catch(err => console.log("Sound autoplay blocked:", err));
    
    // Add ringing shake animation to status bar bell icon
    btnManualBell.classList.add('ringing');
    setTimeout(() => {
        btnManualBell.classList.remove('ringing');
    }, 1800);
}

// Helper: Escape HTML
function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag] || tag)
    );
}
