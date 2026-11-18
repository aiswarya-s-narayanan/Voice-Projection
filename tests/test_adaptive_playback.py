from avatar_kiosk.playback import Playback

PCM = b'\1\0' * 640
SILENCE = bytes(1280)


def player():
    now = [0.0]
    p = Playback(mode='adaptive', clock=lambda: now[0])
    p.reset('a')
    return p, now


def test_sustained_fast_render_starts_early_and_preserves_packets():
    p, now = player()
    for i in range(100):
        now[0] = i/40  # Consistent 40 packets/sec, including three rate windows.
        p.add('a', PCM, b'jpeg')
    assert p.early_ready and not p.finished
    result = []
    for i in range(100):
        result.append(p.next(100+i*.04))
        p.image_at(100+i*.04)
    p.finish('a')
    assert b''.join(result) == PCM*100
    p.image_at(104.1)
    assert p.turn is None and p.underruns == 0


def test_slow_or_barely_realtime_render_waits_until_complete():
    for rate in (10, 25, 28):
        p, now = player()
        for i in range(100):
            now[0] = i/rate
            p.add('a', PCM, b'jpeg')
            assert p.next(50+i*.04) == SILENCE
        assert not p.started
        p.finish('a')
        assert p.next(60) == PCM


def test_single_fast_burst_cannot_trigger_early_start():
    p, now = player()
    for i in range(100):
        p.add('a', PCM, b'jpeg')
    assert p.next(1) == SILENCE
    now[0] = 5
    p.add('a', PCM, b'jpeg')
    assert p.next(6) == SILENCE


def test_unexpected_stall_pauses_once_and_disables_future_early_starts():
    p, now = player()
    for i in range(80):
        now[0] = i/40
        p.add('a', PCM, b'jpeg')
    for i in range(80):
        assert p.next(i*.04) == PCM
        p.image_at(i*.04)
    assert p.next(4) == SILENCE
    assert p.rebuffering and p.underruns == 1 and p.adaptive_failed
    for i in range(100):
        now[0] += .025
        p.add('a', PCM, b'jpeg')
        assert p.next(5+i*.04) == SILENCE
    assert p.underruns == 1
    p.finish('a')
    assert p.next(10) == PCM
    p.reset('b')
    assert not p.rebuffering and not p.rates and p.adaptive_failed
    p.finish('a')
    assert not p.finished


def test_interrupt_clears_rate_history_and_short_replies_play_on_done():
    p, now = player()
    for i in range(80):
        now[0] = i/40
        p.add('a', PCM, b'jpeg')
    assert p.early_ready
    p.reset('b')
    assert not p.rates and not p.early_ready
    p.add('a', PCM, b'stale')
    p.add('b', PCM, b'new')
    assert p.next(3) == SILENCE
    p.finish('b')
    assert p.next(4) == PCM
