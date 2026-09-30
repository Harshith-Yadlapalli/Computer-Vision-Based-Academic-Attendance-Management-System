import os
from PIL import Image
import numpy as np

SOURCE = r"E:\dataset-attendance\FACE-dataset\images.cv_ysfqy3a5ifatbxbhighe1\data\train\faces"
TARGET = r"E:\dataset-attendance\clean_faces"

os.makedirs(TARGET, exist_ok=True)

for student_id in os.listdir(SOURCE):
    src_dir = os.path.join(SOURCE, student_id)
    if not os.path.isdir(src_dir):
        continue

    tgt_dir = os.path.join(TARGET, student_id)
    os.makedirs(tgt_dir, exist_ok=True)

    for i, file in enumerate(os.listdir(src_dir)):
        if not file.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        src_path = os.path.join(src_dir, file)
        tgt_path = os.path.join(tgt_dir, f"{student_id}_{i}.jpg")

        try:
            img = Image.open(src_path)
            img = img.convert("RGB")
            img = img.resize((256, 256))

            arr = np.array(img, dtype=np.uint8)
            img = Image.fromarray(arr)

            img.save(tgt_path, format="JPEG", quality=95)
            print(f"✔ Saved {tgt_path}")

        except Exception as e:
            print(f"❌ Failed {src_path}: {e}")

print("\n✅ Image sanitization complete")
