"""
train.py
========
Trains the from-scratch NumPy LSTM as a character-level language
model on a plain text file, using:

    - Truncated Backpropagation Through Time (chop long text into
      fixed-length chunks; carry hidden/cell state between chunks)
    - Plain Stochastic Gradient Descent (SGD) parameter updates
    - Global-norm gradient clipping (prevents exploding gradients)

Usage
-----
    python train.py --data path/to/text.txt --hidden_size 128 \
                     --seq_length 25 --learning_rate 0.1 --epochs 20

If --data is omitted, a small built-in sample text is used so the
script works out of the box for a quick demo/sanity check.
"""

import argparse
import numpy as np

from lstm import LSTM
from utils import (
    build_vocab, clip_gradients, sequence_batches,
    save_model, load_text,
)


# A tiny built-in fallback corpus, used only if the user doesn't pass
# --data, so the script is runnable "out of the box" for a quick demo.
DEMO_TEXT = (
    "the quick brown fox jumps over the lazy dog. "
    "she sells seashells by the seashore. "
    "how much wood would a woodchuck chuck if a woodchuck could chuck wood. "
) * 50


def parse_args():
    parser = argparse.ArgumentParser(description="Train a from-scratch NumPy LSTM char-level language model.")
    parser.add_argument("--data", type=str, default=None,
                         help="Path to a plain text file to train on. If omitted, uses a small built-in demo corpus.")
    parser.add_argument("--hidden_size", type=int, default=128,
                         help="Number of hidden units in the LSTM.")
    parser.add_argument("--seq_length", type=int, default=25,
                         help="Length of each truncated-BPTT training chunk (in characters).")
    parser.add_argument("--learning_rate", type=float, default=0.1,
                         help="SGD learning rate.")
    parser.add_argument("--epochs", type=int, default=20,
                         help="Number of full passes over the training text.")
    parser.add_argument("--clip_norm", type=float, default=5.0,
                         help="Maximum global gradient norm for clipping.")
    parser.add_argument("--print_every", type=int, default=100,
                         help="Print loss every N training chunks.")
    parser.add_argument("--save_path", type=str, default="model.pkl",
                         help="Where to save the trained model parameters.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args()


def main():
    args = parse_args()
    np.random.seed(args.seed)

    # -----------------------------------------------------------------
    # 1. Load text and build the character vocabulary.
    # -----------------------------------------------------------------
    text = load_text(args.data) if args.data else DEMO_TEXT
    chars, char_to_idx, idx_to_char = build_vocab(text)
    vocab_size = len(chars)
    data_indices = [char_to_idx[ch] for ch in text]

    print(f"Corpus length: {len(text)} characters")
    print(f"Vocabulary size: {vocab_size} unique characters")
    print(f"Vocabulary: {''.join(chars)!r}")

    # -----------------------------------------------------------------
    # 2. Build the model.
    # -----------------------------------------------------------------
    model = LSTM(vocab_size=vocab_size, hidden_size=args.hidden_size, seed=args.seed)

    # -----------------------------------------------------------------
    # 3. Training loop.
    #
    # We use TRUNCATED BPTT: the full corpus is far too long to
    # backpropagate through in one shot (both computationally and
    # because gradients would vanish/explode over that many steps), so
    # instead we slice it into `seq_length`-character chunks and only
    # backpropagate within each chunk. The hidden/cell state (h, c) is
    # carried FORWARD from the end of one chunk to the start of the
    # next, so the model still has access to a "memory" of everything
    # before the current chunk, even though gradients aren't
    # propagated back that far. Whenever we wrap around to the start
    # of the corpus we reset (h, c) to zero, since there's no
    # meaningful "previous chunk" at that point.
    # -----------------------------------------------------------------

    # Exponentially-smoothed loss for a more readable training curve
    # (raw per-chunk loss is noisy). smooth_loss = -log(1/vocab_size)
    # is the expected loss of a randomly-initialized model, i.e. a
    # reasonable starting value for the running average.
    smooth_loss = -np.log(1.0 / vocab_size) * args.seq_length
    chunk_count = 0

    for epoch in range(args.epochs):
        h = np.zeros((args.hidden_size, 1))
        c = np.zeros((args.hidden_size, 1))

        for inputs, targets in sequence_batches(data_indices, args.seq_length):
            # ---- forward pass: unroll the LSTM across this chunk ----
            caches, probs, h, c = model.forward(inputs, h, c)

            # ---- backward pass: BPTT within this chunk ----
            grads, loss = model.backward(inputs, targets, caches, probs)

            # ---- clip gradients to avoid exploding updates ----
            grads = clip_gradients(grads, max_norm=args.clip_norm)

            # ---- SGD parameter update ----
            model.update_params(grads, args.learning_rate)

            # ---- detach hidden state from this chunk's graph ----
            # (Not strictly required in a from-scratch NumPy
            # implementation since we don't have autograd tape to
            # worry about, but conceptually this is the point where a
            # framework like PyTorch would need `.detach()`. Here we
            # simply keep the numeric values of h, c and carry them
            # into the next chunk's forward() call.)

            smooth_loss = 0.999 * smooth_loss + 0.001 * loss
            chunk_count += 1

            if chunk_count % args.print_every == 0:
                print(f"epoch {epoch + 1}/{args.epochs}  "
                      f"chunk {chunk_count}  "
                      f"loss {loss:.4f}  "
                      f"smooth_loss {smooth_loss:.4f}")

        print(f"--- finished epoch {epoch + 1}/{args.epochs} "
              f"(smooth_loss={smooth_loss:.4f}) ---")

    # -----------------------------------------------------------------
    # 4. Save the trained model + vocabulary for later use by predict.py
    # -----------------------------------------------------------------
    save_model(model.params, char_to_idx, idx_to_char, args.save_path)
    print(f"Saved trained model to '{args.save_path}'")


if __name__ == "__main__":
    main()
