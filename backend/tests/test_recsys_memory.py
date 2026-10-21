import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from recsys_memory import limit_embedding_batch  # noqa: E402


def fake_recsys():
    calls = []

    def generate_post_vector(model, tokenizer, texts, batch_size):
        calls.append(batch_size)
        return ("vectors", model, tokenizer, texts)

    return types.SimpleNamespace(generate_post_vector=generate_post_vector), calls


def test_the_recommender_embeds_in_small_batches():
    recsys, calls = fake_recsys()

    limit_embedding_batch(recsys, 64)
    result = recsys.generate_post_vector("model", "tokenizer", ["a", "b"], batch_size=1000)

    assert calls == [64]
    assert result == ("vectors", "model", "tokenizer", ["a", "b"])


def test_a_smaller_batch_asked_for_is_kept():
    recsys, calls = fake_recsys()

    limit_embedding_batch(recsys, 64)
    recsys.generate_post_vector("model", "tokenizer", [], 16)

    assert calls == [16]


def test_applying_it_twice_does_not_wrap_twice():
    recsys, calls = fake_recsys()

    limit_embedding_batch(recsys, 64)
    limit_embedding_batch(recsys, 32)
    recsys.generate_post_vector("model", "tokenizer", [], batch_size=1000)

    assert calls == [32]
