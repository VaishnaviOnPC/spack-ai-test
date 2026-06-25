import json
import os
import urllib.error
import urllib.request


class LLMClient:
    def __init__(self, model="claude-haiku-4-5"):
        self.model = model

    def _provider(self):
        if self.model.startswith("claude"):
            return "anthropic"
        if self.model.startswith("gemini"):
            return "gemini"
        return "openai"

    def _ask_anthropic(self, messages):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        system = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        payload = json.dumps({
            "model": self.model,
            "max_tokens": 512,
            "system": system,
            "messages": user_messages,
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"LLM API error {e.code}: {e.read().decode()}") from e

        return result["content"][0]["text"]

    def _ask_openai(self, messages):
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"LLM API error {e.code}: {e.read().decode()}") from e

        return result["choices"][0]["message"]["content"]

    def _ask_gemini(self, messages):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        # Gemini requires alternating user/model turns, so merge all
        # user context layers into a single message.
        system = ""
        user_parts = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_parts.append(msg["content"])

        body = {
            "contents": [
                {"role": "user", "parts": [{"text": "\n\n".join(user_parts)}]}
            ]
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        payload = json.dumps(body).encode()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{self.model}:generateContent?key={api_key}"
        )

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"content-type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"LLM API error {e.code}: {e.read().decode()}") from e

        return result["candidates"][0]["content"]["parts"][0]["text"]

    def ask(self, messages: list) -> str:
        provider = self._provider()
        if provider == "anthropic":
            return self._ask_anthropic(messages)
        if provider == "gemini":
            return self._ask_gemini(messages)
        return self._ask_openai(messages)
