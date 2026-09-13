from __future__ import annotations

from ollie.domain.codes import ALPHABET, CODE_LENGTH, generate_code, is_valid_code


def test_alphabet_excludes_ambiguous_characters() -> None:
    # Read aloud over the phone, these are the ones that get misheard.
    for excluded in ("0", "O", "I", "1"):
        assert excluded not in ALPHABET


def test_generate_code_shape() -> None:
    for _ in range(200):
        code = generate_code()
        assert len(code) == CODE_LENGTH
        assert all(ch in ALPHABET for ch in code)
        assert is_valid_code(code)


def test_generate_code_is_reasonably_unpredictable() -> None:
    codes = {generate_code() for _ in range(500)}
    # secrets-backed generation over a 32-char alphabet^6 space; 500
    # draws colliding would indicate something is badly wrong.
    assert len(codes) == 500


def test_is_valid_code_rejects_wrong_length() -> None:
    assert not is_valid_code("ABCDE")
    assert not is_valid_code("ABCDEFG")
    assert not is_valid_code("")


def test_is_valid_code_rejects_excluded_characters() -> None:
    assert not is_valid_code("ABCD0F")  # zero
    assert not is_valid_code("ABCDOF")  # letter O
    assert not is_valid_code("ABCD1F")  # one
    assert not is_valid_code("ABCDIF")  # letter I


def test_is_valid_code_rejects_lowercase() -> None:
    assert not is_valid_code("abcdef")
