import threading
import unittest

from prototype.feedback import FeedbackManager, FeedbackSnapshot
from prototype.types import Narration


class Engine:
    def __init__(self):
        self.texts = []
        self.busy = False
        self.stops = 0
        self.fail = False

    def start(self, text):
        if self.fail:
            raise RuntimeError("Không có giọng Việt")
        assert not self.busy, "Hai câu phát đồng thời"
        self.busy = True
        self.texts.append(text)

    def poll(self):
        return None if self.busy else "done"

    def stop(self):
        self.busy = False
        self.stops += 1

    def close(self):
        self.stop()


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.engine = Engine()
        self.manager = FeedbackManager(self.engine, clock=lambda: self.now, autostart=False)
        self.manager.set_context("s", True)
        self.manager._step()

    def tearDown(self):
        self.manager.close()

    def item(self, frame=1, key="person:left", session="s", captured=None, expires=None):
        return Narration("Có " + key + ".", (key,), session, frame,
                         self.now if captured is None else captured,
                         self.now + 2 if expires is None else expires)

    def test_only_latest_pending_and_dedup(self):
        self.manager.submit(self.item(1))
        self.manager._step()
        self.manager.submit(self.item(2))
        self.manager.submit(self.item(3))
        self.assertEqual(self.manager._pending.frame_id, 3)
        self.engine.busy = False
        self.manager._step()
        self.assertEqual(len(self.engine.texts), 1)
        self.now += 6
        self.manager.submit(self.item(4))
        self.manager._step()
        self.assertEqual(len(self.engine.texts), 2)

    def test_new_scene_stops_old_speech(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.manager.submit(self.item(2, "car:right"))
        self.manager._step()
        self.assertEqual(self.engine.texts[-1], "Có car:right.")
        self.assertGreaterEqual(self.engine.stops, 2)

    def test_ttl_not_extended_by_processing(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.now += 2
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.assertFalse(self.manager.submit(self.item(2, captured=9, expires=11)))

    def test_disconnect_and_late_session(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.manager.set_context("new", False)
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.manager.set_context("new", True)
        self.assertFalse(self.manager.submit(self.item(2)))
        self.assertTrue(self.manager.submit(self.item(1, session="new")))

    def test_mute_empty_scene_and_error(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.manager.set_enabled(False)
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.assertFalse(self.manager.submit(self.item(2)))
        self.manager.set_enabled(True)
        self.manager.submit(self.item(3))
        self.manager._step()
        self.manager.submit(None)
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.engine.fail = True
        self.manager.submit(self.item(4, "car:center"))
        self.manager._step()
        self.assertIn("Không có giọng Việt", self.manager.snapshot().error)

    def test_old_frame_and_future_timestamp_rejected(self):
        self.assertTrue(self.manager.submit(self.item(2)))
        self.assertFalse(self.manager.submit(self.item(1)))
        self.assertFalse(self.manager.submit(self.item(3, captured=11)))

    def test_unmute_can_replay_current_fresh_frame_but_rejects_expired_frame(self):
        item = self.item()
        self.manager.submit(item)
        self.manager._step()
        self.manager.set_enabled(False)
        self.manager._step()
        self.manager.set_enabled(True)
        self.assertTrue(self.manager.submit(item))
        self.manager._step()
        self.assertEqual(len(self.engine.texts), 2)
        self.manager.set_enabled(False)
        self.manager._step()
        self.now = 13.0
        self.manager.set_enabled(True)
        self.assertFalse(self.manager.submit(item))

    def test_stop_failure_prevents_another_start_until_confirmed(self):
        self.manager.submit(self.item())
        self.manager._step()
        original_stop = self.engine.stop

        def fail_stop():
            raise RuntimeError("Engine chưa dừng")

        self.engine.stop = fail_stop
        self.manager.submit(self.item(2, "car:right"))
        self.manager._step()
        self.manager._step()
        self.assertEqual(len(self.engine.texts), 1)
        self.assertIn("chưa dừng", self.manager.snapshot().error)
        self.assertEqual(self.manager.snapshot().pending_count, 0)
        self.engine.stop = original_stop
        self.manager._step()
        self.assertIsNone(self.manager.snapshot().error)
        self.manager.submit(self.item(3, "car:right"))
        self.manager._step()
        self.assertEqual(len(self.engine.texts), 2)

    def test_snapshot_new_diagnostics_have_backward_compatible_defaults(self):
        snapshot = FeedbackSnapshot(True, "ready", "", 0, None)
        self.assertEqual(snapshot.utterances_started, 0)
        self.assertEqual(snapshot.utterances_completed, 0)
        self.assertEqual(snapshot.utterances_cancelled, 0)
        self.assertEqual(snapshot.last_event, "")
        self.assertIsNone(snapshot.evidence_captured_at)
        self.assertIsNone(snapshot.evidence_frame_id)

    def test_fresh_matching_evidence_outlives_original_ttl_without_rewriting_utterance(self):
        original = self.item()
        self.manager.submit(original)
        self.manager._step()
        self.now = 11.5
        latest = self.item(2)
        self.assertTrue(self.manager.submit(latest))
        self.manager._step()
        self.now = 12.1
        self.manager._step()
        self.assertTrue(self.engine.busy)
        self.assertIs(self.manager._active, original)
        self.assertEqual(self.manager._active.source_captured_at, 10.0)
        self.assertEqual(self.manager._active.expires_at, 12.0)
        snapshot = self.manager.snapshot()
        self.assertEqual(snapshot.evidence_captured_at, 11.5)
        self.assertEqual(snapshot.evidence_frame_id, 2)
        self.assertEqual(snapshot.utterances_started, 1)
        self.assertEqual(snapshot.utterances_cancelled, 0)
        self.now = 13.5
        self.manager._step()
        self.assertFalse(self.engine.busy)
        snapshot = self.manager.snapshot()
        self.assertEqual(snapshot.utterances_cancelled, 1)
        self.assertEqual(snapshot.last_event, "cancelled:ttl")
        self.assertIsNone(snapshot.evidence_captured_at)

    def test_same_frame_or_same_capture_time_cannot_renew_evidence(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.now = 11.0
        # Even a forged longer expiry cannot turn the same source frame into
        # fresh evidence; frame id AND source timestamp must advance.
        self.assertFalse(self.manager.submit(self.item(1, captured=10.0, expires=30.0)))
        self.assertTrue(self.manager.submit(self.item(2, captured=10.0, expires=12.0)))
        self.manager._step()
        self.assertEqual(self.manager.snapshot().evidence_frame_id, 1)
        self.assertEqual(self.manager.snapshot().evidence_captured_at, 10.0)
        self.now = 12.0
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.assertEqual(self.manager.snapshot().utterances_cancelled, 1)

    def test_expired_utterance_is_cancelled_before_new_matching_frame_can_start(self):
        original = self.item()
        self.manager.submit(original)
        self.manager._step()
        self.now = 12.1
        latest = self.item(2)
        self.manager.submit(latest)
        # submit does not replace or revive the old utterance/evidence.
        self.assertIs(self.manager._active, original)
        self.assertEqual(self.manager.snapshot().evidence_frame_id, 1)
        self.manager._step()
        self.assertIs(self.manager._active, latest)
        self.assertEqual(self.manager.snapshot().utterances_cancelled, 1)
        self.assertEqual(self.manager.snapshot().utterances_started, 2)

    def test_superset_evidence_preserves_exact_spoken_text_and_group_loss_cancels(self):
        original = Narration("Có người ở bên trái. Có ô tô ở bên phải.",
                             ("person:left", "car:right"), "s", 1, 10.0, 12.0)
        self.manager.submit(original)
        self.manager._step()
        stops_before = self.engine.stops
        self.now = 10.5
        reordered = Narration("Có ô tô ở bên phải. Có người ở bên trái. Có biển báo dừng ở giữa ảnh.",
                              ("car:right", "stop sign:center", "person:left"), "s", 2, 10.5, 12.5)
        self.manager.submit(reordered)
        self.manager._step()
        self.assertEqual(self.engine.stops, stops_before)
        self.assertEqual(self.engine.texts, [original.text])
        self.assertEqual(self.manager.snapshot().speaking_text, original.text)
        self.assertEqual(self.manager.snapshot().evidence_frame_id, 2)
        self.assertIs(self.manager._active, original)
        self.now = 11.0
        self.manager.submit(self.item(3, "person:left"))
        self.manager._step()
        self.assertGreater(self.engine.stops, stops_before)
        self.assertEqual(self.manager.snapshot().utterances_cancelled, 1)

    def test_aborted_startup_does_not_suppress_immediate_same_group_retry(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.now = 10.2
        self.manager.submit(None)
        self.manager._step()
        self.assertEqual(self.manager.snapshot().last_event, "cancelled:no_detection")
        self.now = 10.3
        self.manager.submit(self.item(2))
        self.manager._step()
        snapshot = self.manager.snapshot()
        self.assertEqual(len(self.engine.texts), 2)
        self.assertEqual(snapshot.utterances_started, 2)
        self.assertEqual(snapshot.utterances_completed, 0)
        self.assertEqual(snapshot.utterances_cancelled, 1)

    def test_empty_scene_and_unavailable_context_cancel_renewed_evidence_immediately(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.now = 11.0
        self.manager.submit(self.item(2))
        self.manager._step()
        self.manager.set_context("s", False)
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.assertEqual(self.manager.snapshot().last_event, "cancelled:camera_or_model_unavailable")
        self.manager.set_context("s", True)
        self.now = 11.1
        self.manager.submit(self.item(3))
        self.manager._step()
        self.manager.submit(None)
        self.manager._step()
        self.assertFalse(self.engine.busy)
        self.assertEqual(self.manager.snapshot().last_event, "cancelled:no_detection")
        self.assertEqual(self.manager.snapshot().utterances_cancelled, 2)


class DelayedPlaybackTests(unittest.TestCase):
    def test_continuous_fresh_evidence_allows_two_point_five_second_startup(self):
        now = [10.0]

        class DelayedEngine(Engine):
            def start(self, text):
                super().start(text)
                self.started_at = now[0]

            def poll(self):
                if self.busy and now[0] - self.started_at >= 2.5:
                    self.busy = False
                    return "done"
                return None

        engine = DelayedEngine()
        manager = FeedbackManager(engine, clock=lambda: now[0], autostart=False)
        try:
            manager.set_context("s", True)
            for frame in range(50):
                now[0] = 10.0 + frame / 10
                manager.submit(Narration("Có người ở bên trái.", ("person:left",),
                                         "s", frame, now[0], now[0] + 2.0))
                manager._step()
            snapshot = manager.snapshot()
            self.assertEqual(engine.texts, ["Có người ở bên trái."])
            self.assertEqual(snapshot.utterances_started, 1)
            self.assertEqual(snapshot.utterances_completed, 1)
            self.assertEqual(snapshot.utterances_cancelled, 0)
            self.assertEqual(snapshot.last_event, "completed")
        finally:
            manager.close()


class BlockingEngine(Engine):
    def __init__(self):
        super().__init__()
        self.block = None
        self.entered = threading.Event()
        self.resume = threading.Event()

    def wait_if_blocked(self, operation):
        if self.block == operation:
            self.entered.set()
            if not self.resume.wait(2):
                raise RuntimeError("Test did not release the blocked engine")

    def start(self, text):
        self.wait_if_blocked("start")
        super().start(text)

    def poll(self):
        self.wait_if_blocked("poll")
        return super().poll()

    def stop(self):
        self.wait_if_blocked("stop")
        super().stop()


class FeedbackConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.engine = BlockingEngine()
        self.manager = FeedbackManager(self.engine, clock=lambda: 10.0, autostart=False)
        self.manager.set_context("s", True)
        self.manager._step()
        self.threads = []

    def tearDown(self):
        self.engine.resume.set()
        for thread in self.threads:
            thread.join(2)
        self.manager.close()

    def item(self, frame=1, key="person:left", session="s"):
        return Narration("Có " + key + ".", (key,), session, frame, 10.0, 12.0)

    def step_in_thread(self):
        thread = threading.Thread(target=self.manager._step, daemon=True)
        self.threads.append(thread)
        thread.start()
        self.assertTrue(self.engine.entered.wait(1))
        return thread

    def assert_ui_is_responsive(self, action):
        completed = threading.Event()

        def run():
            action()
            self.manager.snapshot()
            completed.set()

        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        self.assertTrue(completed.wait(0.2), "Engine IO held the UI state lock")

    def test_context_changed_during_start_cancels_before_keeping_active(self):
        self.engine.block = "start"
        self.manager.submit(self.item())
        worker = self.step_in_thread()
        self.assert_ui_is_responsive(lambda: self.manager.set_context("new", False))
        self.engine.resume.set()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertFalse(self.engine.busy)
        self.assertEqual(self.manager.snapshot().speaking_text, "")
        self.assertEqual(len(self.engine.texts), 1)

    def test_mute_and_snapshot_do_not_wait_for_stop_and_late_stop_keeps_new_epoch(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.manager.set_enabled(False)
        self.engine.block = "stop"
        worker = self.step_in_thread()

        def change_context():
            self.manager.set_context("new", True)
            self.manager.set_enabled(True)
            self.manager.submit(self.item(1, "car:right", "new"))

        self.assert_ui_is_responsive(change_context)
        self.engine.resume.set()
        worker.join(1)
        # The stop that began before the context change cannot consume the
        # newer cancellation generation or start an obsolete pending sentence.
        self.assertEqual(len(self.engine.texts), 1)
        self.manager._step()
        self.assertEqual(self.engine.texts[-1], "Có car:right.")
        self.assertEqual(len(self.engine.texts), 2)

    def test_empty_scene_during_start_cancels_inflight_utterance(self):
        self.engine.block = "start"
        self.manager.submit(self.item())
        worker = self.step_in_thread()
        self.assert_ui_is_responsive(lambda: self.manager.submit(None))
        self.engine.resume.set()
        worker.join(1)
        self.assertFalse(self.engine.busy)
        self.assertEqual(self.manager.snapshot().pending_count, 0)

    def test_scene_change_during_start_preserves_only_latest_pending(self):
        self.engine.block = "start"
        self.manager.submit(self.item())
        worker = self.step_in_thread()

        def change_scene():
            self.manager.submit(self.item(2, "car:right"))
            self.manager.submit(self.item(3, "stop sign:center"))

        self.assert_ui_is_responsive(change_scene)
        self.engine.resume.set()
        worker.join(1)
        self.assertFalse(self.engine.busy)
        self.manager._step()
        self.assertEqual(self.engine.texts, ["Có person:left.", "Có stop sign:center."])

    def test_poll_does_not_lock_context_change(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.engine.block = "poll"
        worker = self.step_in_thread()
        self.assert_ui_is_responsive(lambda: self.manager.set_enabled(False))
        self.engine.resume.set()
        worker.join(1)
        self.manager._step()
        self.assertFalse(self.engine.busy)

    def test_evidence_update_during_blocked_poll_keeps_utterance_identity_for_completion(self):
        original = self.item()
        self.manager.submit(original)
        self.manager._step()
        self.engine.block = "poll"
        worker = self.step_in_thread()
        self.assert_ui_is_responsive(lambda: self.manager.submit(self.item(2)))
        self.assertIs(self.manager._active, original)
        # Same capture time does not refresh. Use a genuinely newer supporting
        # source while the engine poll is still in progress.
        self.manager._clock = lambda: 10.5
        latest = Narration("Nội dung xếp thứ tự khác.", ("person:left",), "s", 3, 10.5, 12.5)
        self.assertTrue(self.manager.submit(latest))
        self.assertEqual(self.manager.snapshot().evidence_frame_id, 3)
        self.engine.busy = False
        self.engine.resume.set()
        worker.join(1)
        snapshot = self.manager.snapshot()
        self.assertFalse(worker.is_alive())
        self.assertEqual(snapshot.utterances_completed, 1)
        self.assertEqual(snapshot.utterances_cancelled, 0)
        self.assertEqual(snapshot.speaking_text, "")
        self.assertEqual(len(self.engine.texts), 1)

    def test_late_poll_completion_cannot_seed_dedup_after_session_change(self):
        self.manager.submit(self.item())
        self.manager._step()
        self.engine.block = "poll"
        worker = self.step_in_thread()

        def change_session():
            self.manager.set_context("new", True)
            self.manager.submit(self.item(1, session="new"))

        self.assert_ui_is_responsive(change_session)
        self.engine.busy = False
        self.engine.resume.set()
        worker.join(1)
        self.assertEqual(self.manager.snapshot().utterances_completed, 0)
        self.assertEqual(self.manager.snapshot().utterances_cancelled, 1)
        self.manager._step()
        self.assertEqual(len(self.engine.texts), 2)
        self.assertEqual(self.manager.snapshot().utterances_started, 2)


if __name__ == "__main__":
    unittest.main()
