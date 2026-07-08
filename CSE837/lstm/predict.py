"""
predict.py
==========
Loads a trained LSTM model (saved by train.py) and uses it to
generate new text, character by character, in an autoregressive
fashion: at each step the model's own sampled output is fed back in
as the input for the next step.

Usage
-----
    python predict.py --model model.pkl --seed_text "the quick" \
                       --length 200 --temperature 0.8
"""

import argparse
import numpy as np

from lstm import LSTM
from utils import load_model


def parse_args():
    parser = argparse.ArgumentParser(description="Generate text from a trained from-scratch NumPy LSTM.")
    parser.add_argument("--model", type=str, default="model.pkl",
                         help="Path to the saved model file (from train.py).")
    parser.add_argument("--seed_text", type=str, default="the",
                         help="A short prompt string to 'warm up' the model's hidden state before generating.")
    parser.add_argument("--length", type=int, default=200,
                         help="Number of characters to generate.")
    parser.add_argument("--temperature", type=float, default=1.0,
                         help="Sampling temperature. <1.0 = more conservative/repetitive, "
                              ">1.0 = more random/creative.")
    parser.add_argument("--hidden_size", type=int, default=None,
                         help="Hidden size used during training. If omitted, it is inferred "
                              "automatically from the shape of the loaded weight matrices.")
    return parser.parse_args()


def infer_hidden_size(params):
    """
    The saved parameters don't explicitly store hidden_size, but we
    can recover it from the shape of any gate's bias vector (shape
    (hidden_size, 1)).
    """
    return params["bf"].shape[0]


def main():
    args = parse_args()

    # -----------------------------------------------------------------
    # 1. Load trained parameters + vocabulary.
    # -----------------------------------------------------------------
    params, char_to_idx, idx_to_char = load_model(args.model)
    vocab_size = len(char_to_idx)
    hidden_size = args.hidden_size or infer_hidden_size(params)

    # -----------------------------------------------------------------
    # 2. Rebuild an LSTM object with the correct shapes, then overwrite
    #    its randomly-initialized parameters with the trained ones.
    # -----------------------------------------------------------------
    model = LSTM(vocab_size=vocab_size, hidden_size=hidden_size)
    model.params = params

    # -----------------------------------------------------------------
    # 3. "Warm up" the hidden state by running the seed text through
    #    the model's forward pass first, so generation continues
    #    naturally from the prompt rather than from a blank state.
    #    Any characters in seed_text that aren't in the training
    #    vocabulary are simply skipped with a warning.
    # -----------------------------------------------------------------
    h = np.zeros((hidden_size, 1))
    c = np.zeros((hidden_size, 1))

    seed_indices = []
    for ch in args.seed_text:
        if ch in char_to_idx:
            seed_indices.append(char_to_idx[ch])
        else:
            print(f"Warning: character {ch!r} not in training vocabulary, skipping.")

    if not seed_indices:
        # Fall back to the first character in the vocabulary if the
        # entire seed text was unusable.
        seed_indices = [0]

    if len(seed_indices) > 1:
        # Run everything except the last seed character through
        # forward() just to build up hidden state...
        caches, probs, h, c = model.forward(seed_indices[:-1], h, c)

    last_idx = seed_indices[-1]

    # -----------------------------------------------------------------
    # 4. Autoregressively sample new characters.
    # -----------------------------------------------------------------
    generated_indices = model.sample(
        seed_index=last_idx,
        h_prev=h,
        c_prev=c,
        n_chars=args.length,
        temperature=args.temperature,
    )

    generated_text = "".join(idx_to_char[i] for i in generated_indices)

    print("--- Prompt ---")
    print(args.seed_text)
    print("--- Generated continuation ---")
    print(generated_text)


if __name__ == "__main__":
    main()
