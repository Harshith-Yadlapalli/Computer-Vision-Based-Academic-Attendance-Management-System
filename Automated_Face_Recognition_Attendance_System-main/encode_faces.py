import os
import cv2
import face_recognition
import pickle

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.environ.get("FACE_DATASET_PATH", os.path.join(BASE_DIR, "clean_faces"))
ENCODINGS_PATH = os.path.join(BASE_DIR, "encodings.pickle")

if not os.path.isdir(DATASET_PATH):
    raise SystemExit(f"Face dataset folder not found: {DATASET_PATH}")

known_encodings = []
known_names = []

for student_id in os.listdir(DATASET_PATH):
    student_folder = os.path.join(DATASET_PATH, student_id)

    if not os.path.isdir(student_folder):
        continue

    print(f"[INFO] Processing {student_id}")

    for file in os.listdir(student_folder):
        if not file.lower().endswith((".jpg", ".png", ".jpeg")):
            continue

        img_path = os.path.join(student_folder, file)

        image = cv2.imread(img_path)
        if image is None:
            print(f"[ERROR] Could not read {file}")
            continue

        height, width = image.shape[:2]
        scale = min(1.0, 1200 / max(height, width))
        if scale < 1.0:
            image = cv2.resize(image, (int(width * scale), int(height * scale)))

        # OpenCV → RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        boxes = face_recognition.face_locations(
            rgb,
            model="hog",
            number_of_times_to_upsample=1
        )


        if len(boxes) == 0:
            print(f"[WARN] No face detected in {img_path}")
            continue


        encodings = face_recognition.face_encodings(rgb, boxes)

        for encoding in encodings:
            known_encodings.append(encoding)
            known_names.append(student_id)
            print(f"[OK] Encoded {student_id} from {file}")

print(f"\n[OK] Encoded {len(known_encodings)} face images successfully")

if not known_encodings:
    raise SystemExit("No faces were encoded. Add usable student photos before starting CCTV attendance.")

data = {
    "encodings": known_encodings,
    "names": known_names
}

with open(ENCODINGS_PATH, "wb") as f:
    pickle.dump(data, f)

print("💾 Encodings saved to encodings.pickle") 
# py -3.10 -m venv venv -- to get into venv
#venv\Scripts\activate
