import io
import time
import unittest
import urllib.error
import wave

from prototype.speech import SpeechError
from prototype.vieneu_speech import VieNeuSpeechEngine


def make_wav(seconds=0.05, rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\0\0" * int(rate * seconds))
    return buffer.getvalue()


class FakePlayer:
    def __init__(self):
        self.played, self.stops = [], 0

    def play(self, wav):
        self.played.append(wav)

    def stop(self):
        self.stops += 1


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def wait_for(engine, expected, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = engine.poll()
        if result == expected:
            return result
        time.sleep(0.005)
    raise AssertionError("poll không trả kết quả mong đợi")


class VieNeuEngineTests(unittest.TestCase):
    def engine(self, opener, player=None):
        return VieNeuSpeechEngine("vn_sk_secret", opener=opener, player=player or FakePlayer())

    def test_missing_key_is_rejected(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SpeechError):
                VieNeuSpeechEngine(player=FakePlayer())

    def test_success_plays_then_done_once(self):
        player, wav = FakePlayer(), make_wav()
        engine = self.engine(lambda request, timeout: FakeResponse(wav), player)
        engine.start("Có người ở bên trái.")
        self.assertEqual(wait_for(engine, "done"), "done")
        self.assertEqual(player.played, [wav])
        self.assertIsNone(engine.poll())

    def test_http_error_hides_key_and_raises(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

        engine = self.engine(opener)
        engine.start("xin chào")
        with self.assertRaises(SpeechError) as ctx:
            wait_for(engine, "done")
        self.assertNotIn("vn_sk_secret", str(ctx.exception))

    def test_non_wav_is_rejected(self):
        engine = self.engine(lambda request, timeout: FakeResponse(b"<html>"))
        engine.start("xin chào")
        with self.assertRaises(SpeechError):
            wait_for(engine, "done")

    def test_stop_discards_late_response(self):
        player = FakePlayer()
        engine = self.engine(lambda request, timeout: (time.sleep(0.1), FakeResponse(make_wav()))[1], player)
        engine.start("xin chào")
        engine.stop()
        time.sleep(0.25)
        self.assertIsNone(engine.poll())
        self.assertEqual(player.played, [])

    def test_second_start_while_active_is_rejected(self):
        engine = self.engine(lambda request, timeout: FakeResponse(make_wav(1.0)))
        engine.start("một")
        with self.assertRaises(SpeechError):
            engine.start("hai")
        engine.stop()

    def test_cached_sentence_plays_instantly_without_second_http_request(self):
        calls, player, wav = [], FakePlayer(), make_wav(0.05)

        def opener(request, timeout):
            calls.append(request.full_url)
            return FakeResponse(wav)

        engine = self.engine(opener, player)
        engine.start("Có vật cản ở bên trái, đi sang phải.")
        self.assertEqual(wait_for(engine, "done"), "done")
        self.assertEqual(len(calls), 1)
        engine.start("Có vật cản ở bên trái, đi sang phải.")
        self.assertEqual(wait_for(engine, "done"), "done")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(player.played), 2)


if __name__ == "__main__":
    unittest.main()
