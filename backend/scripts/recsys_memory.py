"""
Caps the batch OASIS's Twitter recommender (twhin-bert) embeds at once.

Every round, recsys.rec_sys_personalized_twh embeds every user profile plus
every post with batch_size=1000. The tokenizer pads each batch to its longest
text, and the profiles run to 512 tokens, so one batch of N texts holds
N x 512 x 512 attention scores per head and layer on the CPU: about 9 GB at
250 texts, growing with every post until the machine runs out of memory.
Smaller batches give the same vectors (padding is masked) with a peak that no
longer grows with the run.
"""

from types import ModuleType
from typing import Any


def limit_embedding_batch(recsys: ModuleType, max_batch: int) -> None:
    original = getattr(recsys.generate_post_vector, "__wrapped__", recsys.generate_post_vector)

    def generate_post_vector(model: Any, tokenizer: Any, texts: Any, batch_size: int) -> Any:
        return original(model, tokenizer, texts, min(batch_size, max_batch))

    generate_post_vector.__wrapped__ = original
    recsys.generate_post_vector = generate_post_vector
