"""Consistent loudness is the cheapest form of consistent quality.

Nothing in the render normalises audio, so every clip goes out at whatever level its dub and
its background music happen to produce. Watching one clip you never notice; scrolling a feed
of them, the jumps are the most obvious defect in the batch. One ffmpeg filter at the point
where the deliverable's audio is encoded fixes it for every video at once.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.render_pipeline.audio_loudness import (
    DEFAULT_TARGET_LUFS,
    background_mix_gain,
    build_two_pass_loudnorm_filter,
    build_loudnorm_filter,
    loudness_filter_args,
    loudness_normalization_enabled,
    loudness_target_lufs,
    measure_loudnorm_first_pass,
    two_pass_loudness_filter_args,
)


class SettingsTests(unittest.TestCase):
    def test_background_mix_gain_is_configurable_and_clamped(self) -> None:
        self.assertEqual(
            background_mix_gain(SimpleNamespace(render_background_mix_gain=0.3)),
            0.3,
        )
        self.assertEqual(
            background_mix_gain(SimpleNamespace(render_background_mix_gain=3.0)),
            1.0,
        )

    def test_normalization_is_on_by_default(self) -> None:
        self.assertTrue(loudness_normalization_enabled(SimpleNamespace()))

    def test_it_can_be_turned_off(self) -> None:
        self.assertFalse(loudness_normalization_enabled(SimpleNamespace(render_loudness_normalization_enabled=False)))

    def test_target_comes_from_settings(self) -> None:
        self.assertEqual(loudness_target_lufs(SimpleNamespace(render_loudness_target_lufs=-16.0)), -16.0)

    def test_a_positive_target_is_rejected_as_a_typo(self) -> None:
        self.assertEqual(
            loudness_target_lufs(SimpleNamespace(render_loudness_target_lufs=14.0)),
            DEFAULT_TARGET_LUFS,
            "LUFS targets are negative; a positive value would blow out every render",
        )

    def test_garbage_falls_back_to_the_default(self) -> None:
        self.assertEqual(loudness_target_lufs(SimpleNamespace(render_loudness_target_lufs="loud")), DEFAULT_TARGET_LUFS)


class FilterTests(unittest.TestCase):
    def test_filter_carries_target_true_peak_and_range(self) -> None:
        value = build_loudnorm_filter(target_lufs=-14.0)

        self.assertTrue(value.startswith("loudnorm="))
        self.assertIn("I=-14", value)
        self.assertIn("TP=", value)
        self.assertIn("LRA=", value)

    def test_true_peak_stays_below_zero_to_avoid_clipping(self) -> None:
        value = build_loudnorm_filter(target_lufs=-14.0)
        true_peak = float(value.split("TP=")[1].split(":")[0])

        self.assertLess(true_peak, 0.0)

    def test_args_are_empty_when_disabled(self) -> None:
        self.assertEqual(loudness_filter_args(SimpleNamespace(render_loudness_normalization_enabled=False)), [])

    def test_args_are_an_af_pair_when_enabled(self) -> None:
        args = loudness_filter_args(SimpleNamespace(render_loudness_target_lufs=-14.0))

        self.assertEqual(len(args), 2)
        self.assertEqual(args[0], "-af")
        self.assertIn("loudnorm", args[1])

    def test_two_pass_filter_uses_measured_authority(self) -> None:
        measured = {
            "input_i": -19.97,
            "input_tp": -0.07,
            "input_lra": 3.2,
            "input_thresh": -30.1,
            "target_offset": -0.2,
        }
        value = build_two_pass_loudnorm_filter(measured, target_lufs=-14.0)
        self.assertIn("measured_I=-19.97", value)
        self.assertIn("measured_TP=-0.07", value)
        self.assertIn("linear=true", value)

    def test_first_pass_measurement_builds_second_pass_args(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        payload = (
            '{"input_i":"-19.97","input_tp":"-0.07",'
            '"input_lra":"3.20","input_thresh":"-30.10",'
            '"target_offset":"-0.20"}'
        )

        def fake_run(command, **kwargs):
            return SimpleNamespace(returncode=0, stdout="", stderr=payload)

        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "approved.wav"
            audio.write_bytes(b"RIFF-audio")
            measured = measure_loudnorm_first_pass(
                audio,
                target_lufs=-14.0,
                run=fake_run,
            )
            args = two_pass_loudness_filter_args(
                audio,
                settings=SimpleNamespace(render_loudness_target_lufs=-14.0),
                run=fake_run,
            )
        self.assertEqual(measured["input_i"], -19.97)
        self.assertEqual(args[0], "-af")
        self.assertIn("measured_thresh=-30.1", args[1])
        self.assertIn("TP=-2.7", args[1])


class RunnerTests(unittest.TestCase):
    def _export(self, settings: SimpleNamespace) -> list[str]:
        from src.render_pipeline.runners.ffmpeg_runner import FfmpegRenderRunner
        from src.render_pipeline.types import ExportInput, RenderProfile, VideoProbe

        completed = MagicMock(returncode=0, stdout="", stderr="")
        export_input = ExportInput(
            source_video_path="/tmp/source.mp4",
            narration_path="/tmp/narration.wav",
            subtitle_path=__file__,
            output_path="/tmp/out.mp4",
            profile=RenderProfile(),
            source_probe=VideoProbe(width=1080, height=1920, fps=30.0, duration_seconds=28.0),
        )
        with (
            patch("src.render_pipeline.runners.ffmpeg_runner.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("src.render_pipeline.runners.ffmpeg_runner.subprocess.run", return_value=completed) as run,
            patch("src.render_pipeline.audio_loudness.get_settings", return_value=settings),
        ):
            FfmpegRenderRunner().export(export_input)
        return list(run.call_args.args[0])

    def test_the_deliverable_is_normalised(self) -> None:
        command = self._export(SimpleNamespace(render_loudness_target_lufs=-14.0))

        self.assertIn("-af", command)
        self.assertTrue(any("loudnorm" in part for part in command))

    def test_the_filter_sits_before_the_output_path(self) -> None:
        command = self._export(SimpleNamespace(render_loudness_target_lufs=-14.0))

        self.assertLess(command.index("-af"), len(command) - 1)
        self.assertEqual(command[-1], "/tmp/out.mp4")

    def test_disabling_it_restores_the_previous_command(self) -> None:
        command = self._export(SimpleNamespace(render_loudness_normalization_enabled=False))

        self.assertNotIn("-af", command)

    def test_audio_is_re_encoded_not_copied_so_the_filter_applies(self) -> None:
        command = self._export(SimpleNamespace(render_loudness_target_lufs=-14.0))

        self.assertIn("-c:a", command)
        self.assertNotEqual(command[command.index("-c:a") + 1], "copy")


if __name__ == "__main__":
    unittest.main()
