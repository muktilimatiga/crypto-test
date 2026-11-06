# Please make sure the requests library is installed
# pip install requests
import json
import os
import re
import sys
import time

import requests

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
TOKEN = "641c9511d96b5e3a48d92353728590bbc07c4a3a"
MODEL = "PaddleOCR-VL-1.6"

HEADERS = {"Authorization": f"bearer {TOKEN}"}

OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}


def _image_size(file_path):
    """Return (width, height) of a local image, or None if unreadable."""
    try:
        import cv2
        img = cv2.imread(file_path)
        if img is not None:
            h, w = img.shape[:2]
            return w, h
    except Exception:
        pass
    return None


def _scale_bbox(bbox, img_w, img_h):
    """Convert a raw bbox to integer pixel coords (x1, y1, x2, y2).

    PaddleOCR may return normalized coords (0-1); detect and scale.
    """
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox[:4])
    except (TypeError, ValueError):
        return None
    if img_w and img_h and max(x1, y1, x2, y2) <= 1.0:
        x1, y1, x2, y2 = x1 * img_w, y1 * img_h, x2 * img_w, y2 * img_h
    return (int(x1), int(y1), int(x2), int(y2))


def _extract_rows(result, img_w=None, img_h=None):
    """Pull {text, bbox, label} rows out of one layoutParsingResults entry."""
    rows = []
    for res in result.get("layoutParsingResults", []):
        pruned = res.get("prunedResult") or {}
        parsing = pruned.get("parsing_res_list") or []
        for item in parsing:
            text = (item.get("block_content") or "").strip()
            if not text:
                continue
            rows.append({
                "text": text,
                "bbox": _scale_bbox(item.get("block_bbox"), img_w, img_h),
                "label": item.get("block_label") or "",
            })
        if not parsing:
            # Fallback: markdown lines without coordinates
            md = (res.get("markdown") or {}).get("text") or ""
            for line in md.splitlines():
                line = line.strip()
                if line:
                    rows.append({"text": line, "bbox": None, "label": "text"})
    return rows


def ocr_scan(file_path, image_size=None, poll_interval=5, timeout=300):
    """Run the cloud OCR job and return a list of {text, bbox, label} dicts.

    file_path: local image path or http(s) URL.
    image_size: optional (width, height) used to scale normalized bboxes.
    Raises RuntimeError on submission/poll failure.
    """
    print(f"Processing file: {file_path}")

    if image_size is None and not file_path.startswith("http"):
        image_size = _image_size(file_path)

    headers = dict(HEADERS)
    if file_path.startswith("http"):
        headers["Content-Type"] = "application/json"
        payload = {
            "fileUrl": file_path,
            "model": MODEL,
            "optionalPayload": OPTIONAL_PAYLOAD,
        }
        job_response = requests.post(JOB_URL, json=payload, headers=headers)
    else:
        if not os.path.exists(file_path):
            raise RuntimeError(f"File not found at {file_path}")
        data = {
            "model": MODEL,
            "optionalPayload": json.dumps(OPTIONAL_PAYLOAD),
        }
        with open(file_path, "rb") as f:
            files = {"file": f}
            job_response = requests.post(JOB_URL, headers=headers, data=data, files=files)

    print(f"Response status: {job_response.status_code}")
    if job_response.status_code != 200:
        raise RuntimeError(f"OCR submit failed: {job_response.text}")

    job_id = job_response.json()["data"]["jobId"]
    print(f"Job submitted successfully. job id: {job_id}")

    deadline = time.time() + timeout
    jsonl_url = ""
    while True:
        if time.time() > deadline:
            raise RuntimeError(f"OCR job {job_id} timed out after {timeout}s")
        job_result_response = requests.get(f"{JOB_URL}/{job_id}", headers=headers)
        if job_result_response.status_code != 200:
            raise RuntimeError(f"OCR poll failed: {job_result_response.text}")
        data = job_result_response.json()["data"]
        state = data["state"]
        if state == "pending":
            print("The current status of the job is pending")
        elif state == "running":
            progress = data.get("extractProgress") or {}
            print(f"running... {progress.get('extractedPages', '?')}/{progress.get('totalPages', '?')} pages")
        elif state == "done":
            jsonl_url = data["resultUrl"]["jsonUrl"]
            print("Job completed")
            break
        elif state == "failed":
            raise RuntimeError(f"OCR job failed: {data.get('errorMsg')}")
        time.sleep(poll_interval)

    jsonl_response = requests.get(jsonl_url)
    jsonl_response.raise_for_status()

    img_w = img_h = None
    if image_size:
        img_w, img_h = image_size

    rows = []
    for line in jsonl_response.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        result = json.loads(line)["result"]
        rows.extend(_extract_rows(result, img_w, img_h))
    return rows


if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "<local file path or file url>"

    try:
        rows = ocr_scan(file_path)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Extracted {len(rows)} text blocks:")
    for r in rows:
        print(f"  {r['bbox']}  {r['text']!r}")
