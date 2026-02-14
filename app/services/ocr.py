import google.generativeai as genai
from PIL import Image
import json
import time
import io


EXTRACTION_PROMPT = """Analyze this receipt image and extract all information.
Return ONLY valid JSON:
{
    "merchant_name": "Store name",
    "merchant_address": "Address or null",
    "date": "YYYY-MM-DD",
    "time": "HH:MM or null",
    "currency": "JPY",
    "line_items": [{"description": "Item", "quantity": 1, "unit_price": 0, "total_price": 0}],
    "subtotal": 0,
    "tax_amount": 0,
    "tax_rate": "10%",
    "total_amount": 0,
    "payment_method": "Cash/Card",
    "category": "Food/Household/Transportation/Entertainment/Healthcare/Clothing/Electronics/Other",
    "confidence": 0.95
}
Rules: 合計=total, 小計=subtotal, 税=tax. Return ONLY JSON."""


class OCRService:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def process_image(self, image_bytes: bytes) -> dict:
        """Process a receipt image and return structured OCR data."""
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        start = time.time()
        response = self.model.generate_content([EXTRACTION_PROMPT, image])

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        result = json.loads(text)
        result["processing_time_ms"] = (time.time() - start) * 1000
        return result
