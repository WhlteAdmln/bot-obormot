from bot.utils.text import utf16_length


def test_utf16_length_counts_basic_and_non_bmp_characters():
    assert utf16_length("hello") == 5
    assert utf16_length("a😀b") == 4
    assert utf16_length("") == 0
