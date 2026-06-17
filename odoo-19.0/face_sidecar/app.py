import base64
import math
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

ENGINE_NAME = "local-opencv-hybrid-v2"
FACE_SIZE = 112
MAX_SAMPLES = 7

app = FastAPI(title="ELSx Face Attendance Sidecar", version="1.2.0")

_FRONTAL = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_PROFILE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
_EYES = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


class EnrollRequest(BaseModel):
    image: Optional[str] = None
    images: List[str] = []


class ScanRequest(BaseModel):
    image: Optional[str] = None


class VerifyCandidate(BaseModel):
    id: int
    embedding: Any


class VerifyRequest(BaseModel):
    image: Optional[str] = None
    images: List[str] = []
    candidates: List[VerifyCandidate]
    threshold: float = 0.78


def _decode_image(image_data: str) -> np.ndarray:
    if not image_data:
        raise ValueError("image is required")
    if "," in image_data and image_data.split(",", 1)[0].startswith("data:"):
        image_data = image_data.split(",", 1)[1]
    raw = base64.b64decode(image_data)
    buffer = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("image could not be decoded")
    return image


def _sample_images(primary: Optional[str], images: List[str]) -> List[np.ndarray]:
    payloads = [item for item in (images or []) if item]
    if primary and primary not in payloads:
        payloads.insert(0, primary)
    if not payloads:
        raise ValueError("image is required")
    return [_decode_image(item) for item in payloads[:MAX_SAMPLES]]


def _clip_box(box, width: int, height: int, expand: float = 0.22):
    x, y, w, h = [int(v) for v in box]
    pad_x = int(w * expand)
    pad_y = int(h * expand)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(width, x + w + pad_x)
    y2 = min(height, y + h + pad_y)
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def _detect_faces(gray: np.ndarray) -> List[tuple]:
    equalized = cv2.equalizeHist(gray)
    faces = list(_FRONTAL.detectMultiScale(equalized, scaleFactor=1.08, minNeighbors=5, minSize=(72, 72)))
    profiles = list(_PROFILE.detectMultiScale(equalized, scaleFactor=1.08, minNeighbors=5, minSize=(72, 72)))
    flipped = cv2.flip(equalized, 1)
    flipped_profiles = _PROFILE.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=5, minSize=(72, 72))
    width = gray.shape[1]
    for x, y, w, h in flipped_profiles:
        profiles.append((width - x - w, y, w, h))
    boxes = faces + profiles
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda item: item[2] * item[3], reverse=True)
    selected = []
    for box in boxes:
        x, y, w, h = box
        duplicate = False
        for sx, sy, sw, sh in selected:
            ix1 = max(x, sx)
            iy1 = max(y, sy)
            ix2 = min(x + w, sx + sw)
            iy2 = min(y + h, sy + sh)
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            union = (w * h) + (sw * sh) - inter
            if union and inter / union > 0.35:
                duplicate = True
                break
        if not duplicate:
            selected.append(tuple(int(v) for v in box))
    return selected


def _aligned_face(gray: np.ndarray, box: tuple) -> Dict[str, Any]:
    height, width = gray.shape[:2]
    x, y, w, h = _clip_box(box, width, height)
    crop = gray[y:y + h, x:x + w]
    crop = _CLAHE.apply(crop)
    upper = crop[: max(1, int(crop.shape[0] * 0.62)), :]
    eyes = list(_EYES.detectMultiScale(upper, scaleFactor=1.08, minNeighbors=5, minSize=(14, 14)))
    eye_score = 0.0
    angle = 0.0
    if len(eyes) >= 2:
        eyes = sorted(eyes, key=lambda item: item[2] * item[3], reverse=True)[:2]
        eyes = sorted(eyes, key=lambda item: item[0])
        left = (eyes[0][0] + eyes[0][2] / 2.0, eyes[0][1] + eyes[0][3] / 2.0)
        right = (eyes[1][0] + eyes[1][2] / 2.0, eyes[1][1] + eyes[1][3] / 2.0)
        if abs(right[0] - left[0]) > 8:
            angle = math.degrees(math.atan2(right[1] - left[1], right[0] - left[0]))
            matrix = cv2.getRotationMatrix2D((crop.shape[1] / 2.0, crop.shape[0] / 2.0), angle, 1.0)
            crop = cv2.warpAffine(crop, matrix, (crop.shape[1], crop.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            eye_score = 1.0
    resized = cv2.resize(crop, (FACE_SIZE, FACE_SIZE), interpolation=cv2.INTER_AREA)
    normalized = _CLAHE.apply(resized)
    return {
        "face": normalized,
        "box": [int(v) for v in box],
        "expanded_box": [int(x), int(y), int(w), int(h)],
        "eye_score": eye_score,
        "angle": round(float(angle), 2),
    }


def _lbp_hist(face: np.ndarray) -> np.ndarray:
    center = face[1:-1, 1:-1]
    codes = np.zeros(center.shape, dtype=np.uint8)
    neighbors = [
        face[:-2, :-2], face[:-2, 1:-1], face[:-2, 2:],
        face[1:-1, 2:], face[2:, 2:], face[2:, 1:-1],
        face[2:, :-2], face[1:-1, :-2],
    ]
    for idx, neighbor in enumerate(neighbors):
        codes |= ((neighbor >= center) << idx).astype(np.uint8)
    cells = []
    cell_h = codes.shape[0] // 4
    cell_w = codes.shape[1] // 4
    for row in range(4):
        for col in range(4):
            patch = codes[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w]
            hist = np.bincount(patch.flatten(), minlength=256).astype(np.float32)
            hist /= float(hist.sum()) or 1.0
            cells.append(hist)
    return np.concatenate(cells)


def _dct_features(face: np.ndarray) -> np.ndarray:
    small = cv2.resize(face, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    coeff = cv2.dct(small)[:16, :16].flatten()
    coeff[0] = 0.0
    return coeff.astype(np.float32)


def _gradient_hist(face: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(face, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(face, cv2.CV_32F, 0, 1, ksize=3)
    mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    bins = np.floor((angle % 180) / 20).astype(np.int32)
    features = []
    cell_h = face.shape[0] // 4
    cell_w = face.shape[1] // 4
    for row in range(4):
        for col in range(4):
            b = bins[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w]
            m = mag[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w]
            hist = np.zeros(9, dtype=np.float32)
            for idx in range(9):
                hist[idx] = float(m[b == idx].sum())
            hist /= float(np.linalg.norm(hist)) or 1.0
            features.append(hist)
    return np.concatenate(features)


def _vector(face: np.ndarray) -> List[float]:
    vector = np.concatenate([_lbp_hist(face) * 0.58, _dct_features(face) * 0.28, _gradient_hist(face) * 0.14]).astype(np.float32)
    vector -= float(vector.mean())
    vector /= float(np.linalg.norm(vector)) or 1.0
    return [round(float(v), 6) for v in vector.tolist()]


def _quality(image: np.ndarray, gray: np.ndarray, face: np.ndarray, box: tuple, face_count: int, eye_score: float) -> Dict[str, Any]:
    x, y, w, h = box
    image_h, image_w = gray.shape[:2]
    face_area = (w * h) / float(image_h * image_w)
    blur = float(cv2.Laplacian(face, cv2.CV_64F).var())
    brightness = float(face.mean())
    contrast = float(face.std())
    center_x = x + w / 2.0
    center_y = y + h / 2.0
    centered = 1.0 - min(1.0, (abs(center_x - image_w / 2.0) / (image_w / 2.0) + abs(center_y - image_h / 2.0) / (image_h / 2.0)) / 1.45)
    area_score = max(0.0, min(1.0, face_area / 0.11))
    blur_score = max(0.0, min(1.0, blur / 220.0))
    brightness_score = 1.0 - min(1.0, abs(brightness - 126.0) / 126.0)
    contrast_score = max(0.0, min(1.0, contrast / 58.0))
    multi_face_penalty = 0.82 if face_count > 1 else 1.0
    score = (
        area_score * 0.24 +
        blur_score * 0.22 +
        brightness_score * 0.16 +
        contrast_score * 0.15 +
        centered * 0.13 +
        eye_score * 0.10
    ) * multi_face_penalty
    warnings = []
    if face_area < 0.035:
        warnings.append("move closer to the camera")
    if blur < 45:
        warnings.append("image is blurry")
    if brightness < 55:
        warnings.append("increase lighting")
    if brightness > 205:
        warnings.append("reduce harsh lighting")
    if contrast < 18:
        warnings.append("face contrast is low")
    if face_count > 1:
        warnings.append("multiple faces detected")
    status = "good" if score >= 0.72 else "usable" if score >= 0.48 else "poor"
    return {
        "quality": round(float(max(0.0, min(1.0, score))), 4),
        "quality_status": status,
        "warnings": warnings,
        "blur": round(blur, 2),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "face_area": round(float(face_area), 4),
        "centered": round(float(centered), 4),
    }


def _embedding_for_image(image: np.ndarray) -> Dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = _detect_faces(gray)
    if not faces:
        raise ValueError("no clear face found")
    box = max(faces, key=lambda item: item[2] * item[3])
    aligned = _aligned_face(gray, box)
    metrics = _quality(image, gray, aligned["face"], box, len(faces), aligned["eye_score"])
    return {
        "vector": _vector(aligned["face"]),
        "face_count": int(len(faces)),
        "face_box": aligned["box"],
        "quality": metrics["quality"],
        "quality_status": metrics["quality_status"],
        "warnings": metrics["warnings"],
        "metrics": metrics,
        "alignment": {
            "eye_score": aligned["eye_score"],
            "angle": aligned["angle"],
        },
    }


def _scan_image(image: np.ndarray) -> Dict[str, Any]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = _detect_faces(gray)
    if not faces:
        return {
            "ok": True,
            "engine": ENGINE_NAME,
            "face_count": 0,
            "quality": 0.0,
            "quality_status": "no_face",
            "warnings": ["no clear face found"],
            "metrics": {},
            "face_box": [],
            "alignment": {},
            "scan_status": "empty",
        }
    box = max(faces, key=lambda item: item[2] * item[3])
    aligned = _aligned_face(gray, box)
    metrics = _quality(image, gray, aligned["face"], box, len(faces), aligned["eye_score"])
    scan_status = "ready"
    if len(faces) > 1:
        scan_status = "multiple_faces"
    elif metrics["quality"] < 0.48:
        scan_status = "poor_quality"
    elif metrics["quality"] < 0.72:
        scan_status = "usable"
    return {
        "ok": True,
        "engine": ENGINE_NAME,
        "face_count": int(len(faces)),
        "quality": metrics["quality"],
        "quality_status": metrics["quality_status"],
        "warnings": metrics["warnings"],
        "metrics": metrics,
        "face_box": aligned["box"],
        "alignment": {
            "eye_score": aligned["eye_score"],
            "angle": aligned["angle"],
        },
        "scan_status": scan_status,
    }


def _average_vectors(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    arr = np.array(vectors, dtype=np.float32)
    centroid = arr.mean(axis=0)
    centroid -= float(centroid.mean())
    centroid /= float(np.linalg.norm(centroid)) or 1.0
    return [round(float(v), 6) for v in centroid.tolist()]


def _build_template(primary: Optional[str], images: List[str], strict: bool) -> Dict[str, Any]:
    decoded = _sample_images(primary, images)
    samples = []
    errors = []
    for image in decoded:
        try:
            sample = _embedding_for_image(image)
            if not strict or sample["quality"] >= 0.42:
                samples.append(sample)
            else:
                errors.append("sample quality too low: %s" % ", ".join(sample.get("warnings") or ["poor image"]))
        except Exception as exc:
            errors.append(str(exc))
    if not samples:
        raise ValueError("; ".join(errors) or "no usable face sample found")
    samples = sorted(samples, key=lambda item: item["quality"], reverse=True)[:5]
    vectors = [sample["vector"] for sample in samples]
    quality = float(sum(sample["quality"] for sample in samples) / len(samples))
    liveness_status = _passive_liveness(samples)
    warnings = []
    for sample in samples:
        warnings.extend(sample.get("warnings") or [])
    warnings.extend(errors)
    return {
        "embedding": {
            "version": 2,
            "engine": ENGINE_NAME,
            "centroid": _average_vectors(vectors),
            "templates": [
                {
                    "vector": sample["vector"],
                    "quality": sample["quality"],
                    "quality_status": sample["quality_status"],
                    "face_box": sample["face_box"],
                    "metrics": sample["metrics"],
                }
                for sample in samples
            ],
            "sample_count": len(samples),
        },
        "quality": round(quality, 4),
        "quality_status": "good" if quality >= 0.72 else "usable" if quality >= 0.48 else "poor",
        "face_count": max(sample["face_count"] for sample in samples),
        "sample_count": len(samples),
        "engine": ENGINE_NAME,
        "liveness_status": liveness_status,
        "warnings": sorted(set(warnings)),
        "metrics": samples[0].get("metrics") or {},
    }


def _passive_liveness(samples: List[Dict[str, Any]]) -> str:
    if len(samples) < 2:
        return "single_frame"
    boxes = np.array([sample["face_box"] for sample in samples], dtype=np.float32)
    qualities = np.array([sample["quality"] for sample in samples], dtype=np.float32)
    movement = float(np.std(boxes[:, :2])) if len(boxes) else 0.0
    quality_delta = float(np.std(qualities)) if len(qualities) else 0.0
    if movement > 0.6 or quality_delta > 0.002:
        return "passed"
    return "uncertain"


def _candidate_vectors(embedding: Any) -> List[List[float]]:
    if isinstance(embedding, list):
        return [embedding]
    if not isinstance(embedding, dict):
        return []
    vectors = []
    centroid = embedding.get("centroid")
    if isinstance(centroid, list):
        vectors.append(centroid)
    for item in embedding.get("templates") or []:
        vector = item.get("vector") if isinstance(item, dict) else None
        if isinstance(vector, list):
            vectors.append(vector)
    return vectors


def _cosine_confidence(probe: List[float], candidate: List[float]) -> float:
    if not probe or not candidate or len(probe) != len(candidate):
        return 0.0
    dot = sum(a * b for a, b in zip(probe, candidate))
    na = math.sqrt(sum(a * a for a in probe)) or 1.0
    nb = math.sqrt(sum(b * b for b in candidate)) or 1.0
    cosine = max(-1.0, min(1.0, dot / (na * nb)))
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


@app.get("/health")
def health():
    return {
        "ok": True,
        "engine": ENGINE_NAME,
        "liveness": "passive_multi_frame",
        "descriptor": "lbp+dct+gradient",
    }


@app.post("/enroll")
def enroll(payload: EnrollRequest):
    try:
        result = _build_template(payload.image, payload.images, strict=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **result}


@app.post("/scan")
def scan(payload: ScanRequest):
    try:
        image = _decode_image(payload.image or "")
        return _scan_image(image)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/verify")
def verify(payload: VerifyRequest):
    try:
        result = _build_template(payload.image, payload.images, strict=False)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    probe_vectors = _candidate_vectors(result["embedding"])
    best = {"id": None, "confidence": 0.0}
    for candidate in payload.candidates:
        for stored in _candidate_vectors(candidate.embedding):
            for probe in probe_vectors:
                confidence = _cosine_confidence(probe, stored)
                if confidence > best["confidence"]:
                    best = {"id": candidate.id, "confidence": confidence}
    verified = bool(best["id"] and best["confidence"] >= payload.threshold)
    return {
        "ok": True,
        "matched_id": best["id"],
        "confidence": round(float(best["confidence"]), 4),
        "verified": verified,
        "threshold": payload.threshold,
        "reason": "matched" if verified else "no candidate reached threshold",
        "quality": result["quality"],
        "quality_status": result["quality_status"],
        "face_count": result["face_count"],
        "sample_count": result["sample_count"],
        "engine": result["engine"],
        "liveness_status": result["liveness_status"],
        "warnings": result["warnings"],
        "metrics": result["metrics"],
    }
