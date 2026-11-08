"""Tests use a fake worker: no audio, camera or Windows voice package required."""

import io
import json
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from prototype.speech import SpeechError, WindowsSpeechEngine, _decode_result, is_vietnamese_language, list_voices, main


class FakeProcess:
    def __init__(self, command, *, stdin, stdout, stderr, **kwargs):
        self.command = command
        self.stdin = io.BytesIO()
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = None
        self.killed = False
        self.waited = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -1

    def wait(self, timeout=None):
        self.waited = True
        return self.returncode

    def finish(self, result, code=0):
        self.stdout.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        self.returncode = code


class SpeechTests(unittest.TestCase):
    def test_cli_sample_uses_manager_and_always_closes_it(self):
        for error in (None, "Không tổng hợp được giọng tiếng Việt."):
            with self.subTest(error=error):
                engine = Mock(last_result=None)
                manager = Mock()
                manager.snapshot.return_value = SimpleNamespace(error=error)

                def submit(sample):
                    self.assertEqual(sample.session_id, "speech-test")
                    self.assertEqual(sample.groups, ("speech-test",))
                    self.assertEqual(sample.expires_at - sample.source_captured_at, 30.0)
                    if error is None:
                        engine.last_result = {"ok": True, "playbackCompleted": True, "heardConfirmed": None}
                    return True

                manager.submit.side_effect = submit
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch("prototype.speech.WindowsSpeechEngine", return_value=engine), \
                     patch("prototype.feedback.FeedbackManager", return_value=manager) as factory, \
                     redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(["--test"])
                self.assertEqual(code, int(error is not None))
                factory.assert_called_once_with(engine)
                manager.set_context.assert_called_once_with("speech-test", healthy=True)
                manager.close.assert_called_once_with()
                for method in (engine.start, engine.poll, engine.stop, engine.close):
                    method.assert_not_called()
                self.assertIn("câu mẫu", stdout.getvalue())
                if error:
                    self.assertIn(error, stderr.getvalue())

    def test_vietnamese_locale_is_explicit(self):
        for language in ("vi", "vi-VN", "VI_vn"):
            self.assertTrue(is_vietnamese_language(language))
        for language in ("en-US", "Microsoft An", "vi-XX", "", "vietnamese"):
            self.assertFalse(is_vietnamese_language(language))

    def test_worker_failure_retains_hresult(self):
        result = {"ok": False, "errors": [{"backend": "winrt", "message": "Access failed", "hresults": ["0x80040154"]}]}
        with self.assertRaisesRegex(SpeechError, "0x80040154"):
            _decode_result(json.dumps(result).encode(), b"", 1)

    def test_invalid_worker_output_is_not_success(self):
        with self.assertRaisesRegex(SpeechError, "JSON"):
            _decode_result(b"", b"activation failed", 0)

    @patch("prototype.speech._command", return_value=["worker", "-File", "trusted.ps1"])
    @patch("prototype.speech.subprocess.Popen", side_effect=FakeProcess)
    def test_completion_is_reported_once_and_shutdown_cannot_restart(self, popen, _command):
        engine = WindowsSpeechEngine()
        engine.start("Có người ở bên trái.")
        worker = engine._process
        self.assertIsNone(engine.poll())
        with self.assertRaises(SpeechError):
            engine.start("Có ô tô ở giữa ảnh.")
        worker.finish({"ok": True, "selectedVoice": {"name": "Microsoft An"}, "playbackCompleted": True, "heardConfirmed": None})
        self.assertEqual(engine.poll(), "done")
        self.assertIsNone(engine.poll())
        self.assertIsNone(engine.last_result["heardConfirmed"])
        engine.close()
        self.assertEqual(popen.call_count, 1)

    @patch("prototype.speech._command", return_value=["worker"])
    @patch("prototype.speech.subprocess.Popen", side_effect=FakeProcess)
    def test_stop_kills_current_audio_and_forgets_late_result(self, _popen, _command):
        engine = WindowsSpeechEngine()
        engine.start("Có người.")
        worker = engine._process
        engine.stop()
        self.assertTrue(worker.killed)
        self.assertTrue(worker.waited)
        self.assertIsNone(engine.poll())
        self.assertIsNone(engine._process)

    @patch("prototype.speech._command", return_value=["worker"])
    @patch("prototype.speech.subprocess.Popen", side_effect=FakeProcess)
    @patch("prototype.speech.time.monotonic", side_effect=[10.0, 41.0])
    def test_timeout_kills_worker_and_surfaces_error(self, _clock, _popen, _command):
        engine = WindowsSpeechEngine(timeout=30)
        engine.start("Có người.")
        worker = engine._process
        with self.assertRaisesRegex(SpeechError, "hết thời gian"):
            engine.poll()
        self.assertTrue(worker.killed)

    @patch("prototype.speech._command", return_value=["worker"])
    @patch("prototype.speech.subprocess.Popen", side_effect=FakeProcess)
    def test_failed_kill_keeps_handle_and_forbids_overlapping_worker(self, popen, _command):
        engine = WindowsSpeechEngine()
        engine.start("Có người.")
        worker = engine._process
        original_kill = worker.kill
        worker.kill = Mock(side_effect=PermissionError("process access denied"))
        with self.assertRaisesRegex(SpeechError, "không hủy được"):
            engine.stop()
        self.assertIs(engine._process, worker)
        with self.assertRaises(SpeechError):
            engine.start("Có ô tô.")
        self.assertEqual(popen.call_count, 1)
        worker.kill = original_kill
        engine.close()
        self.assertIsNone(engine._process)

    @patch("prototype.speech._command", return_value=["worker"])
    @patch("prototype.speech.subprocess.Popen", side_effect=FakeProcess)
    def test_unconfirmed_exit_keeps_handle_until_retry_succeeds(self, popen, _command):
        engine = WindowsSpeechEngine()
        engine.start("Có người.")
        worker = engine._process
        original_wait = worker.wait
        worker.wait = Mock(side_effect=subprocess.TimeoutExpired("worker", 1.0))
        with self.assertRaisesRegex(SpeechError, "chưa xác nhận"):
            engine.stop()
        self.assertIs(engine._process, worker)
        self.assertFalse(engine._stdout.closed)
        with self.assertRaises(SpeechError):
            engine.start("Có ô tô.")
        self.assertEqual(popen.call_count, 1)
        worker.wait = original_wait
        engine.close()
        self.assertIsNone(engine._process)

    @patch("prototype.speech._command", return_value=["worker"])
    @patch("prototype.speech.subprocess.run")
    def test_inventory_request_cannot_play_and_uses_utf8_stdin(self, run, _command):
        result = {"ok": True, "vietnameseInstalled": True, "playbackAttempted": False, "heardConfirmed": None}
        run.return_value = subprocess.CompletedProcess(["worker"], 0, json.dumps(result).encode(), b"")
        self.assertFalse(list_voices()["playbackAttempted"])
        call = run.call_args
        payload = json.loads(call.kwargs["input"].decode("utf-8"))
        self.assertEqual(payload["action"], "probe")
        self.assertIn("người", payload["text"])
        self.assertNotIn("shell", call.kwargs)


if __name__ == "__main__":
    unittest.main()
