from avatar_kiosk.playback import Playback


def test_audio_and_image_follow_dac_clock_and_interrupt_flushes():
    player = Playback()
    player.reset("a")
    pcm = b"\1\0" * 640
    player.add("a", pcm, "mouth-a")
    player.finish("a")
    assert player.next(10) == pcm
    assert player.image_at(9.99) is None
    assert player.image_at(10) == "mouth-a"
    player.add("a", pcm, "stale")
    player.reset("b")
    player.add("a", pcm, "late-stale")
    assert player.next(11) == bytes(1280)
    assert player.image_at(12) is None


def test_underflow_does_not_advance_video():
    player = Playback()
    player.reset("turn")
    assert player.next(1) == bytes(1280)
    assert player.image_at(1) is None
    player.add("turn", bytes(1280), "next")
    player.finish("turn")
    player.next(2)
    assert player.image_at(2) == "next"


def test_slow_bursty_rendering_never_starts_then_inserts_gaps():
    player = Playback()
    player.reset('slow')
    packets = []
    # Render one 40-ms packet every 200 ms, far slower than playback. The
    # previous 3-packet buffer started early and repeatedly inserted silence.
    for i in range(100):
        pcm = (i + 1).to_bytes(2, 'little') * 640
        packets.append(pcm)
        player.add('slow', pcm, b'jpeg')
        for tick in range(5):
            assert player.next(i*.2 + tick*.04) == bytes(1280)
        assert not player.started
    player.finish('slow')
    rendered = []
    for i, expected in enumerate(packets):
        rendered.append(player.next(30 + i*.04))
        assert rendered[-1] == expected
        assert player.image_at(30 + i*.04) == b'jpeg'
    assert b''.join(rendered) == b''.join(packets)
    assert player.buffered_bytes == 0
    player.image_at(34.1)
    assert player.turn is None


def test_long_reply_and_interrupt_during_buffering():
    player = Playback()
    player.reset('long')
    for _ in range(300):  # More than the old 10-second queue limit.
        player.add('long', b'\1\0'*640, b'jpeg')
    assert player.next(1) == bytes(1280)
    player.reset('new')
    player.finish('long')
    player.add('long', b'\1\0'*640, b'stale')
    assert not player.pending and player.buffered_bytes == 0
    assert player.next(2) == bytes(1280)


def test_buffer_is_bounded_and_late_packets_do_not_extend_finished_reply():
    import pytest
    player = Playback()
    player.reset('bounded')
    player.buffered_bytes = 256*1024*1024
    with pytest.raises(RuntimeError, match='buffer limit'):
        player.add('bounded', bytes(1280), b'jpeg')
    player.reset('finished')
    player.add('finished', bytes(1280), b'jpeg')
    player.finish('finished')
    player.add('finished', bytes(1280), b'late')
    assert len(player.pending) == 1
