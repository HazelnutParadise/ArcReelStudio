"""项目设置里的「连线」旁键：跟着同一字段的供应商走。"""

from __future__ import annotations

from server.services.project.project_settings_patch import ProjectSettingsPatch, apply_project_settings_patch


def _apply(project: dict, **values: object) -> dict:
    apply_project_settings_patch(project, ProjectSettingsPatch.model_validate(values))
    return project


def test_a_connection_is_stored_next_to_its_model_field() -> None:
    project = _apply({}, default_image_backend="gemini-aistudio/gemini-3-pro", default_image_backend_credential_id=7)
    assert project["default_image_backend_credential_id"] == 7


def test_clearing_the_connection_returns_to_the_default() -> None:
    project = {"default_image_backend": "gemini-aistudio/gemini-3-pro", "default_image_backend_credential_id": 7}
    _apply(project, default_image_backend_credential_id=None)
    assert "default_image_backend_credential_id" not in project


def test_switching_provider_without_choosing_a_connection_drops_the_old_one() -> None:
    project = {"default_image_backend": "gemini-aistudio/gemini-3-pro", "default_image_backend_credential_id": 7}
    _apply(project, default_image_backend="openai/gpt-image-1")
    assert "default_image_backend_credential_id" not in project


def test_changing_only_the_model_keeps_the_connection() -> None:
    project = {"default_image_backend": "gemini-aistudio/gemini-3-pro", "default_image_backend_credential_id": 7}
    _apply(project, default_image_backend="gemini-aistudio/gemini-3-flash")
    assert project["default_image_backend_credential_id"] == 7


def test_a_connection_without_a_model_field_is_not_kept() -> None:
    project = _apply({}, video_backend_credential_id=3)
    assert "video_backend_credential_id" not in project
