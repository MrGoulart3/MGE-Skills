"""Offline regression tests for portable public-example post-production."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_post(topic: str, script: str):
    """Loads an example with clean environment defaults and no media execution."""
    name = f"example_{script}"
    spec = importlib.util.spec_from_file_location(
        name, EXAMPLES / topic / "post" / f"{script}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with mock.patch.dict(os.environ, {}, clear=True):
        spec.loader.exec_module(module)
    return module


class ExampleRuntimeTest(unittest.TestCase):
    """Verify independent assets, executable selection and both audio paths."""

    @classmethod
    def setUpClass(cls):
        cls.modules = [load_post(topic, script) for topic, script in (
            ("salt-dissolving", "montar_sal"), ("sn2-walden", "montar_sn2"))]

    def test_media_tools_use_path_or_explicit_executable(self):
        for module in self.modules:
            with self.subTest(module=module.__name__):
                with mock.patch.dict(os.environ, {}, clear=True):
                    with mock.patch.object(module.subprocess, "run") as run:
                        module._media_command("ffmpeg", ["-version"], Path("cache"))
                        self.assertEqual(run.call_args.args[0], ["ffmpeg", "-version"])
                with mock.patch.dict(os.environ, {"FFPROBE": "/opt/media tools/ffprobe"}):
                    with mock.patch.object(module.subprocess, "run") as run:
                        module._media_command("ffprobe", ["-version"], Path("cache"))
                        self.assertEqual(run.call_args.args[0],
                                         ["/opt/media tools/ffprobe", "-version"])

    def test_music_is_optional_and_explicit_music_is_mixed(self):
        for module in self.modules:
            for music in (None, Path("licensed music.wav")):
                with self.subTest(module=module.__name__, music=music):
                    with mock.patch.object(module, "MUSIC", music):
                        args = module._encode_arguments(
                            Path("frames"), "%04d.png", Path("overlays"),
                            Path("video.mp4"), 24, {})
                    graph = args[args.index("-filter_complex") + 1]
                    self.assertIn("[2:a]", graph)
                    self.assertIn("[a]", graph)
                    self.assertEqual("[3:a]" in graph, music is not None)
                    self.assertEqual("sidechaincompress" in graph, music is not None)
                    self.assertEqual(args.count("-i"), 3 if music is None else 4)
                    if music is not None:
                        self.assertIn(str(music), args)

    def test_static_fonts_do_not_require_variable_font_axes(self):
        for module in self.modules:
            with self.subTest(module=module.__name__):
                painter = module.Painter.__new__(module.Painter)
                painter.scale, painter.fonts = 1, {}
                font = mock.Mock()
                font.get_variation_axes.side_effect = OSError("not a variable font")
                with mock.patch.object(module.ImageFont, "truetype", return_value=font) as load:
                    self.assertIs(painter._font(30, 700), font)
                    self.assertEqual(load.call_args.args[0], module.FONT)
                    painter._font(30, 700, symbol=True)
                    self.assertEqual(load.call_args.args[0], module.SYMBOL_FONT)
                font.set_variation_by_axes.assert_not_called()

    def test_variable_font_weights_preserve_other_axes(self):
        for module in self.modules:
            with self.subTest(module=module.__name__):
                painter = module.Painter.__new__(module.Painter)
                painter.scale, painter.fonts = 1, {}
                font = mock.Mock()
                font.get_variation_axes.return_value = [
                    {"name": b"Width", "default": 100},
                    {"name": b"Weight", "default": 400}]
                with mock.patch.object(module.ImageFont, "truetype", return_value=font):
                    painter._font(30, 700)
                font.set_variation_by_axes.assert_called_once_with([100, 700])

    def test_frame_validation_rejects_missing_frames(self):
        for module in self.modules:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    folder = Path(directory)
                    for number in (1, 3):
                        module.Image.new("RGB", (64, 36)).save(folder / f"{number:04d}.png")
                    with self.assertRaisesRegex(ValueError, "Quadro ausente"):
                        module._inspect_frames(folder)


if __name__ == "__main__":
    unittest.main()
