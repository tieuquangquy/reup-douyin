from src.services.job_runner import _should_auto_approve_visual


def test_auto_visual_approval_accepts_audio_stage_with_current_preview() -> None:
    assert _should_auto_approve_visual(
        {
            "workflow_stage": "AUDIO_APPROVED",
            "visual_preview_asset_id": "preview-current",
            "visual_approved": False,
        }
    )


def test_auto_visual_approval_does_not_reapprove_existing_visual_authority() -> None:
    assert not _should_auto_approve_visual(
        {
            "workflow_stage": "AUDIO_APPROVED",
            "visual_preview_asset_id": "preview-current",
            "visual_approved": True,
        }
    )


def test_auto_visual_approval_requires_a_preview_artifact_outside_visual_stage() -> None:
    assert not _should_auto_approve_visual(
        {
            "workflow_stage": "AUDIO_APPROVED",
            "visual_preview_asset_id": None,
            "visual_approved": False,
        }
    )
