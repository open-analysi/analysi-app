"""Unit tests for in-memory sliding-window rate limiter."""

from analysi.auth.rate_limit import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    def test_allows_first_attempt(self):
        limiter = SlidingWindowRateLimiter(max_attempts=5)
        assert limiter.check_and_record("key1") is True

    def test_allows_up_to_max_attempts(self):
        limiter = SlidingWindowRateLimiter(max_attempts=5)
        for _ in range(5):
            assert limiter.check_and_record("key1") is True

    def test_blocks_on_sixth_attempt(self):
        limiter = SlidingWindowRateLimiter(max_attempts=5)
        for _ in range(5):
            limiter.check_and_record("key1")
        assert limiter.check_and_record("key1") is False

    def test_different_keys_are_independent(self):
        limiter = SlidingWindowRateLimiter(max_attempts=3)
        for _ in range(3):
            limiter.check_and_record("key-a")
        # key-a is exhausted
        assert limiter.check_and_record("key-a") is False
        # key-b is unaffected
        assert limiter.check_and_record("key-b") is True

    def test_expired_window_resets(self):
        # Use a very short window so we can simulate expiry
        limiter = SlidingWindowRateLimiter(max_attempts=2, window_seconds=1)
        limiter.check_and_record("key1")
        limiter.check_and_record("key1")
        # Exhausted now
        assert limiter.check_and_record("key1") is False

        # Manually push the stored timestamps into the past

        bucket = limiter._buckets["key1"]
        old_timestamps = list(bucket)
        bucket.clear()
        # Put stale timestamps (2 seconds ago)
        for ts in old_timestamps:
            bucket.append(ts - 2)

        # Window should have evicted them — allow again
        assert limiter.check_and_record("key1") is True

    def test_max_attempts_one(self):
        limiter = SlidingWindowRateLimiter(max_attempts=1)
        assert limiter.check_and_record("k") is True
        assert limiter.check_and_record("k") is False
