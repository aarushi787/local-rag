"""Extract readable text from an image with PaddleOCR."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import tempfile
from pathlib import Path

def result_lines(result: object) -> list[dict]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        return []

    data = payload.get("res", payload)
    if not isinstance(data, dict):
        return []
    texts = data.get("rec_texts", [])
    boxes = data.get("rec_boxes", [])
    lines: list[dict] = []
    for index, text in enumerate(texts):
        cleaned = str(text).strip()
        if not cleaned:
            continue
        bbox = None
        if index < len(boxes):
            raw_box = boxes[index]
            if hasattr(raw_box, "tolist"):
                raw_box = raw_box.tolist()
            bbox = [float(value) for value in raw_box]
        lines.append({"text": cleaned, "bbox": bbox})
    return lines


def main() -> None:
    from paddleocr import PaddleOCR

    parser = argparse.ArgumentParser(description="Extract OCR text from an image.")
    parser.add_argument("image", type=Path, help="Path to a PNG or JPG document")
    parser.add_argument("--output", type=Path, default=Path("ocr-output.txt"))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    image = args.image.expanduser().resolve()
    if not image.is_file():
        raise SystemExit(f"Image not found: {image}")

    from PIL import Image

    max_side = max(1200, int(os.getenv("OCR_MAX_SIDE", "2600")))
    prediction_image = image
    with Image.open(image) as image_file:
        original_width, original_height = image_file.size
        if max(image_file.size) > max_side:
            resized = image_file.convert("RGB")
            resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            handle, resized_name = tempfile.mkstemp(prefix="rag-ocr-resized-", suffix=".jpg")
            os.close(handle)
            prediction_image = Path(resized_name)
            atexit.register(prediction_image.unlink, missing_ok=True)
            resized.save(prediction_image, format="JPEG", quality=94)
    with Image.open(prediction_image) as prediction_file:
        prediction_width, prediction_height = prediction_file.size

    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    lines: list[dict] = []
    for result in ocr.predict(str(prediction_image)):
        lines.extend(result_lines(result))

    scale_x = original_width / prediction_width
    scale_y = original_height / prediction_height
    if scale_x != 1 or scale_y != 1:
        for line in lines:
            bbox = line.get("bbox")
            if bbox and len(bbox) == 4:
                line["bbox"] = [
                    round(bbox[0] * scale_x, 2),
                    round(bbox[1] * scale_y, 2),
                    round(bbox[2] * scale_x, 2),
                    round(bbox[3] * scale_y, 2),
                ]

    if not lines:
        raise SystemExit("OCR completed but returned no text.")

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(line["text"] for line in lines) + "\n", encoding="utf-8"
    )
    if args.json_output:
        json_output = args.json_output.expanduser().resolve()
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps({"width": original_width, "height": original_height, "lines": lines}),
            encoding="utf-8",
        )
    print(f"Saved {len(lines)} OCR lines to: {output}")


if __name__ == "__main__":
    main()
