"""用 ChatGPT 订阅（经 Codex 内置的生图）生成图片。订阅只能经官方的 Codex 使用，每次调用起一次 Codex 跑一轮。"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from lib.backends.image_backends.base import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageOutputMissingError,
    ImageRequestFacts,
)
from lib.backends.image_backends.openai import OpenAIImageBackend
from lib.backends.subscription_shared import PROVIDER_CHATGPT_SUBSCRIPTION, SubscriptionCallError
from lib.billing.metering import Usage
from lib.catalog import query as catalog
from lib.subscriptions.codex_turn import CodexTurnError, run_codex_turn


class ChatGPTSubscriptionImageBackend:
    """用 ChatGPT 订阅（经 Codex 内置的生图）生成图片，参考图作为输入图。"""

    def __init__(self, *, codex_home: Path, model: str | None = None) -> None:
        self._home = codex_home
        self._model = model or "gpt-image-2"

    @property
    def name(self) -> str:
        return PROVIDER_CHATGPT_SUBSCRIPTION

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return {ImageCapability.TEXT_TO_IMAGE, ImageCapability.IMAGE_TO_IMAGE}

    async def reference_image_limit(self) -> int | None:
        return None

    @staticmethod
    def estimate_usage(facts: ImageRequestFacts) -> Usage:
        """Codex 生图用的就是 ``gpt-image-2``，按 OpenAI Images 的口径估输出 token（订阅倍率为 0，不计费用）。"""
        return OpenAIImageBackend.estimate_usage(facts)

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        references = [Path(ref.path) for ref in request.reference_images]
        instruction = (
            f"Generate exactly one image with the image generation tool ($imagegen, model {self._model}). "
            f"Aspect ratio {request.aspect_ratio}."
            + (
                " Use the attached images as references, referred to as image 1, image 2 in order."
                if references
                else ""
            )
            + " Do not ask questions; reply only with the image.\n\nImage description:\n"
            + request.prompt
        )
        output_dir = request.output_path.parent / f".{request.output_path.stem}-codex"
        try:
            turn = await run_codex_turn(self._home, instruction, input_images=references, image_output_dir=output_dir)
        except CodexTurnError as exc:
            raise SubscriptionCallError(str(exc), provider=self.name, code=exc.code) from exc
        try:
            if not turn.images:
                raise ImageOutputMissingError(model=self._model)
            await asyncio.to_thread(_place_image, turn.images[0], request.output_path)
        finally:
            await asyncio.to_thread(
                shutil.rmtree, output_dir, True
            )  # hard-delete: temp -- Codex 生图的中转目录，已拷出
        facts = ImageRequestFacts(
            model=self._model,
            aspect_ratio=request.aspect_ratio,
            image_size=request.image_size,
            reference_count=len(references),
            entry=catalog.provider_model_entry(self.name, self._model, "image"),
        )
        return ImageGenerationResult(
            image_path=request.output_path,
            provider=self.name,
            model=self._model,
            usage=self.estimate_usage(facts),
        )


def _place_image(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
