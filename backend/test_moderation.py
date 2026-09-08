from automated_moderation import abuse_velocity, moderate_text


def test_clean_text_is_allowed():
    result = moderate_text("Beautiful sunset today")
    assert result.action == "allow"
    assert result.score == 0


def test_abusive_text_is_reviewed():
    result = moderate_text("go die")
    assert result.action == "review"
    assert "abusive_language" in result.labels


def test_velocity_limit():
    assert abuse_velocity([59, 58, 57], 60, window_seconds=60, limit=3)
