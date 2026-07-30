from __future__ import annotations
from .providers import LLMProvider

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate_json(self, *, system: str, user: str) -> dict:
        # Local import so the app runs without this dependency
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        m = genai.GenerativeModel(self.model)

        prompt = f"{system}\n\n{user}\n\nReturn ONLY valid JSON."
        r = m.generate_content(prompt)
        import json
        return json.loads(r.text)
