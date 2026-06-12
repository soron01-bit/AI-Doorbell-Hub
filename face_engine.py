import os
import json
import uuid
import datetime
import numpy as np
import cv2

class FaceEngine:
    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.base_dir = base_dir
        self.models_dir = os.path.join(base_dir, 'models')
        self.faces_dir = os.path.join(base_dir, 'static', 'registered_faces')
        
        # Ensure directories exist
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.faces_dir, exist_ok=True)
        
        self.registry_file = os.path.join(self.faces_dir, 'registry.json')
        
        # Model paths
        self.yunet_model = os.path.join(self.models_dir, 'face_detection_yunet_2023mar.onnx')
        self.sface_model = os.path.join(self.models_dir, 'face_recognition_sface_2021dec.onnx')
        
        # Check that models exist
        if not os.path.exists(self.yunet_model) or not os.path.exists(self.sface_model):
            raise FileNotFoundError("YuNet or SFace models are missing from the models directory. Please download them first.")
            
        # Initialize Face Detector (YuNet)
        # We start with a default input size of (320, 320). It will be resized dynamically to match the frame size.
        self.detector = cv2.FaceDetectorYN.create(
            model=self.yunet_model,
            config='',
            input_size=(320, 320),
            score_threshold=0.6,  # lower threshold to catch faces in different lighting/glasses
            nms_threshold=0.3,
            top_k=10
        )
        
        # Initialize Face Recognizer (SFace)
        self.recognizer = cv2.FaceRecognizerSF.create(
            model=self.sface_model,
            config=''
        )
        
        # Cache for registered faces: list of dicts {"id": id, "name": name, "embedding": np.array}
        self.registry = []
        self.load_registry()

    def load_registry(self):
        self.registry = []
        if not os.path.exists(self.registry_file):
            with open(self.registry_file, 'w') as f:
                json.dump([], f)
            return

        try:
            with open(self.registry_file, 'r') as f:
                metadata = json.load(f)
                
            for item in metadata:
                emb_path = os.path.join(self.faces_dir, f"{item['id']}.npy")
                if os.path.exists(emb_path):
                    try:
                        embedding = np.load(emb_path)
                        self.registry.append({
                            "id": item["id"],
                            "name": item["name"],
                            "added_at": item.get("added_at", ""),
                            "embedding": embedding
                        })
                    except Exception as e:
                        print(f"Error loading embedding for {item['name']}: {e}")
        except Exception as e:
            print(f"Error reading registry file: {e}")

    def save_registry_metadata(self):
        try:
            metadata = []
            for item in self.registry:
                metadata.append({
                    "id": item["id"],
                    "name": item["name"],
                    "added_at": item["added_at"]
                })
            with open(self.registry_file, 'w') as f:
                json.dump(metadata, f, indent=4)
        except Exception as e:
            print(f"Error saving registry metadata: {e}")

    def get_registered_faces(self):
        """Returns metadata list of registered faces."""
        return [{
            "id": item["id"],
            "name": item["name"],
            "added_at": item["added_at"],
            "image_url": f"/static/registered_faces/{item['id']}.jpg"
        } for item in self.registry]

    def detect_faces(self, frame):
        """
        Detect faces in a frame. Resizes internally for speed and robustness,
        then scales the output coordinates back to the original frame size.
        """
        h, w = frame.shape[:2]
        
        # Determine target size (max width 640) for optimal YuNet performance
        max_w = 640
        if w > max_w:
            scale = max_w / w
            target_w = max_w
            target_h = int(h * scale)
            resized = cv2.resize(frame, (target_w, target_h))
        else:
            scale = 1.0
            resized = frame
            target_w = w
            target_h = h
            
        self.detector.setInputSize((target_w, target_h))
        retval, faces = self.detector.detect(resized)
        
        if retval and faces is not None:
            # Scale coordinates back to original size if resized
            if scale != 1.0:
                scaled_faces = faces.copy()
                # Scale the 14 spatial coordinates (bounding box + landmarks)
                scaled_faces[:, 0:14] = scaled_faces[:, 0:14] / scale
                return scaled_faces
            return faces
        return None

    def get_face_embedding(self, frame, face_box):
        """
        Extracts face embedding (128D) from a frame and single face box row.
        """
        try:
            aligned_face = self.recognizer.alignCrop(frame, face_box)
            embedding = self.recognizer.feature(aligned_face)
            return embedding
        except Exception as e:
            print(f"Error generating face embedding: {e}")
            return None

    def match_face(self, embedding, threshold=0.363):
        """
        Compares embedding against registered embeddings.
        Returns (name, score) if matched above threshold, else ('Unknown', score)
        """
        if not self.registry or embedding is None:
            return "Unknown", 0.0
            
        best_name = "Unknown"
        best_score = -1.0
        
        for item in self.registry:
            score = self.recognizer.match(embedding, item["embedding"], cv2.FaceRecognizerSF_FR_COSINE)
            if score > best_score:
                best_score = score
                if score >= threshold:
                    best_name = item["name"]
                    
        return best_name, float(best_score)

    def register_face(self, name, frame, face_box):
        """
        Registers a face from a camera frame and detected face box.
        Saves cropped face image, full image, and embedding.
        """
        embedding = self.get_face_embedding(frame, face_box)
        if embedding is None:
            return None
            
        face_id = str(uuid.uuid4())
        
        # Save embedding
        emb_path = os.path.join(self.faces_dir, f"{face_id}.npy")
        np.save(emb_path, embedding)
        
        # Save cropped face image
        aligned_face = self.recognizer.alignCrop(frame, face_box)
        img_path = os.path.join(self.faces_dir, f"{face_id}.jpg")
        cv2.imwrite(img_path, aligned_face)
        
        # Add to registry
        added_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.registry.append({
            "id": face_id,
            "name": name,
            "added_at": added_at,
            "embedding": embedding
        })
        self.save_registry_metadata()
        
        return {
            "id": face_id,
            "name": name,
            "added_at": added_at,
            "image_url": f"/static/registered_faces/{face_id}.jpg"
        }

    def register_face_from_image(self, name, image_data):
        """
        Registers a face from an image file (numpy array).
        """
        faces = self.detect_faces(image_data)
        if faces is None or len(faces) == 0:
            raise ValueError("No faces detected in the uploaded image.")
            
        # Sort detected faces by bounding box area (w * h) in descending order to select the largest face
        faces_sorted = sorted(faces, key=lambda x: x[2] * x[3], reverse=True)
        face_box = faces_sorted[0]
        return self.register_face(name, image_data, face_box)

    def delete_face(self, face_id):
        """Deletes a face from the registry and files."""
        # Find item
        item_to_remove = None
        for item in self.registry:
            if item["id"] == face_id:
                item_to_remove = item
                break
                
        if not item_to_remove:
            return False
            
        self.registry.remove(item_to_remove)
        self.save_registry_metadata()
        
        # Delete files
        for ext in ['.jpg', '.npy']:
            file_path = os.path.join(self.faces_dir, f"{face_id}{ext}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
                    
        return True
