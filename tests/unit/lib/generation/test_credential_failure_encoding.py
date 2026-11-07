"""设置里指定的连线已不存在时，任务失败原因落成可本地化、提示「重新选择连线」的结构化代码。"""

from __future__ import annotations

from lib.config.resolver import CredentialNotFoundError
from lib.generation.generation_result import GenerationAction, problem_from_task_failure
from lib.generation.task_failure import parse_failure
from lib.generation.task_failure_encoding import encode_task_failure_message


def test_a_deleted_connection_is_reported_as_a_configuration_problem() -> None:
    message = encode_task_failure_message(CredentialNotFoundError(provider_id="gemini-aistudio", credential_id=7))

    assert parse_failure(message) == ("credential_not_found", {"provider": "gemini-aistudio"})


def test_the_failure_asks_for_provider_configuration() -> None:
    message = encode_task_failure_message(CredentialNotFoundError(provider_id="gemini-aistudio", credential_id=7))

    assert problem_from_task_failure(message).action is GenerationAction.CONFIGURE_PROVIDER
