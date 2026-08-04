from scripts.rebind_phase4_audio_authority import (
    contract_with_audio_authority,
    residual_bundle_with_rebound_input,
)


def test_audio_rebind_changes_only_audio_authority_and_final_gate() -> None:
    contract = {
        "status": "READY_FOR_PHASE4",
        "final_render_gate": "BLOCKED_AUDIO_AUTHORITY",
        "render_tracks": [{"text_id": "sub_01"}],
        "authorities": {
            "timebase": {"status": "READY"},
            "audio": {"status": "VISUAL_PREVIEW_ONLY"},
            "color": {"codec": "h264"},
        },
    }
    audio = {
        "status": "READY",
        "strategy": "mix_vietnamese_narration_with_background_stem",
        "narration_ref": {"storage_key": "phase4_joined_narration.wav"},
        "background_ref": {"storage_key": "phase4_background.wav"},
    }

    rebound = contract_with_audio_authority(contract, audio)

    assert rebound["final_render_gate"] == "READY_FOR_FINAL_RENDER"
    assert rebound["authorities"]["audio"] == audio
    assert rebound["authorities"]["timebase"] == contract["authorities"]["timebase"]
    assert rebound["authorities"]["color"] == contract["authorities"]["color"]
    assert rebound["render_tracks"] == contract["render_tracks"]
    assert contract["final_render_gate"] == "BLOCKED_AUDIO_AUTHORITY"


def test_audio_rebind_updates_only_residual_bundle_input_binding() -> None:
    old_hash = "a" * 64
    new_hash = "b" * 64
    bundle = {
        "schema_version": "phase4_residual_cjk_false_positive_approval_v2",
        "status": "OCR_FALSE_POSITIVES_CONFIRMED",
        "authority_refs": {
            "phase4_input": {
                "path": "phase4_render_input.json",
                "sha256": old_hash,
            },
            "immutable_output_qa": {"path": "qa.json", "sha256": "c" * 64},
        },
        "binding": {
            "source_video_sha256": "d" * 64,
            "phase4_input_sha256": old_hash,
        },
        "binding_sha256": "stale",
        "approvals": [{"cluster_id": "outres_1"}],
        "approval_sha256": "stale",
    }

    rebound = residual_bundle_with_rebound_input(
        bundle,
        old_input_sha256=old_hash,
        new_input_sha256=new_hash,
    )

    assert rebound["binding"]["phase4_input_sha256"] == new_hash
    assert rebound["authority_refs"]["phase4_input"]["sha256"] == new_hash
    assert rebound["authority_refs"]["immutable_output_qa"] == bundle["authority_refs"]["immutable_output_qa"]
    assert bundle["binding"]["phase4_input_sha256"] == old_hash
