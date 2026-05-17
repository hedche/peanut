from __future__ import annotations

import asyncio
import json
import logging
import random
import time

from app.metrics import metrics
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError

from app.config import Settings
from app.prompts import SYSTEM_PROMPT
from app.telegram import send_briefing

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    raw_text: str
    parsed_json: list[dict[str, str]]


class GeminiProvider:
    """Google Gemini Developer API provider (AI Studio)."""

    name = "gemini"

    def __init__(self, cfg: Settings):
        if not cfg.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required")

        self.client = genai.Client(api_key=cfg.google_api_key)
        self.model = cfg.gemini_model
        self.cfg = cfg

    async def generate(self, prompt: str) -> LLMResponse:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        raw = response.text
        return LLMResponse(raw_text=raw, parsed_json=json.loads(raw))

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Check if an error is retryable (e.g., 429 rate limit, 503 service unavailable)."""
        if isinstance(exc, ClientError):
            # Handle rate limit errors (429) that have retry info
            if hasattr(exc, "code") and exc.code == 429:
                return True
        if isinstance(exc, ServerError):
            if hasattr(exc, "code") and exc.code == 503:
                return True
        return False


class MultiProviderLLM:
    """Gemini LLM client with retry logic."""

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.provider = GeminiProvider(cfg)
        logger.info("Gemini provider initialized (model: %s)", cfg.gemini_model)

    async def generate_with_fallback(
        self, prompt: str
    ) -> tuple[LLMResponse, str, int]:
        """Generate with retry logic.

        Args:
            prompt: The prompt to send

        Returns:
            Tuple of (response, provider_name, total_retries)

        Raises:
            Exception: If generation fails after all retries
        """
        response = await self._generate_with_retry(prompt)
        return response, self.provider.name, 0

    async def _generate_with_retry(
        self,
        prompt: str,
    ) -> LLMResponse:
        """Generate with retry logic."""
        max_attempts = self.cfg.gemini_retry_max_attempts
        wait_time = self.cfg.gemini_retry_initial_wait
        notified_user = False
        retry_count = 0

        for attempt in range(1, max_attempts + 1):
            start_time = time.perf_counter()
            try:
                response = await self.provider.generate(prompt)
                latency_ms = (time.perf_counter() - start_time) * 1000
                metrics.record_request(
                    self.provider.name,
                    latency_ms=latency_ms,
                    success=True,
                    retries=retry_count,
                )
                return response

            except Exception as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000
                is_retryable = self.provider._is_retryable_error(exc)

                if not is_retryable or attempt == max_attempts:
                    logger.error(
                        "Generation failed on attempt %d/%d (retryable=%s): %s",
                        attempt,
                        max_attempts,
                        is_retryable,
                        exc,
                    )
                    metrics.record_request(
                        self.provider.name,
                        latency_ms=latency_ms,
                        success=False,
                        retries=retry_count,
                    )
                    raise

                # Notify user on first retry
                if not notified_user:
                    await send_briefing(
                        f"⏳ *Peanut is waiting...*\n\n"
                        f"Gemini experiencing high demand. "
                        f"Retrying with exponential backoff (max {max_attempts} attempts).",
                        self.cfg,
                    )
                    notified_user = True

                # Add jitter: random value between 0 and wait_time * 0.5
                jitter = random.uniform(0, wait_time * 0.5)
                sleep_duration = wait_time + jitter

                logger.warning(
                    "Retryable error on attempt %d/%d — waiting %.1fs",
                    attempt,
                    max_attempts,
                    sleep_duration,
                )

                retry_count += 1
                await asyncio.sleep(sleep_duration)

                # Exponential backoff with cap
                wait_time = min(
                    wait_time * self.cfg.gemini_retry_wait_multiplier,
                    self.cfg.gemini_retry_max_wait,
                )

        # Should never reach here
        raise RuntimeError("Unexpected exit from retry loop")
