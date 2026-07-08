"""
utils.py
========
Helper functions that support the LSTM but are not "core LSTM math":

    - reading a text file and building a character <-> index vocabulary
    - one-hot encoding characters into vectors the network can consume
    - Xavier/Glorot-style weight initialization
    - gradient clipping (essential for RNN/LSTM training stability)
    - a simple sequential mini-batch generator for training
    - saving / loading trained parameters to disk (via NumPy's .npz)

Keeping these separate from lstm.py keeps the core model code focused
purely on the forward/backward LSTM math.
"""

import numpy as np
import pickle


# ---------------------------------------------------------------------------
# Text / vocabulary utilities
# ---------------------------------------------------------------------------

def load_text(path):
    """Read an entire text file into a single Python string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_vocab(text):
    """
    Build the character-level vocabulary for a piece of text.

    Returns
    -------
    chars       : sorted list of unique characters (the vocabulary)
    char_to_idx : dict mapping character -> integer index
    idx_to_char : dict mapping integer index -> character
    """
    chars = sorted(list(set(text)))
    char_to_idx = {ch: i for i, ch in enumerate(chars)}
    idx_to_char = {i: ch for i, ch in enumerate(chars)}
    return chars, char_to_idx, idx_to_char


def one_hot(index, vocab_size):
    """
    Turn a single integer index into a one-hot column vector of shape
    (vocab_size, 1). One-hot encoding is how we feed discrete symbols
    (characters) into a network that only understands real-valued
    vectors: every entry is 0 except a single 1 at position `index`.
    """
    vec = np.zeros((vocab_size, 1))
    vec[index, 0] = 1.0
    return vec


def encode_sequence(seq_indices, vocab_size):
    """
    One-hot encode a whole sequence of integer indices at once.

    Parameters
    ----------
    seq_indices : list/array of integers, length T
    vocab_size  : size of the vocabulary

    Returns
    -------
    array of shape (T, vocab_size, 1) - one one-hot column per timestep
    """
    return np.array([one_hot(i, vocab_size) for i in seq_indices])


# ---------------------------------------------------------------------------
# Weight initialization
# ---------------------------------------------------------------------------

def xavier_init(rows, cols, seed=None):
    """
    Xavier/Glorot initialization.

    Randomly initializes a (rows, cols) weight matrix with values drawn
    from a uniform distribution scaled by sqrt(1 / cols). This keeps
    the variance of activations roughly stable as they pass through
    layers, which helps avoid vanishing/exploding activations early in
    training (before the network has learned anything useful).

        W ~ Uniform(-1/sqrt(cols), +1/sqrt(cols))
    """
    if seed is not None:
        np.random.seed(seed)
    limit = 1.0 / np.sqrt(cols)
    return np.random.uniform(-limit, limit, (rows, cols))


# ---------------------------------------------------------------------------
# Gradient clipping
# ---------------------------------------------------------------------------

def clip_gradients(grads, max_norm=5.0):
    """
    In-place gradient clipping by global norm.

    RNNs/LSTMs are notorious for "exploding gradients" during BPTT,
    where gradients grow exponentially as they are propagated back
    through many timesteps. If left unchecked this can produce huge,
    unstable parameter updates (or NaNs).

    This function computes the global L2 norm across *all* gradient
    arrays combined, and if that norm exceeds `max_norm`, it rescales
    every gradient array by the same factor so the new global norm is
    exactly `max_norm`. Scaling every gradient by the same factor
    preserves the *direction* of the overall gradient vector; only its
    magnitude is reduced.

    Parameters
    ----------
    grads    : dict[str, np.ndarray] - gradients keyed by parameter name
    max_norm : float - the maximum allowed global L2 norm

    Returns
    -------
    The same `grads` dict, clipped in place (also returned for
    convenience so callers can chain calls if desired).
    """
    total_norm_sq = 0.0
    for g in grads.values():
        total_norm_sq += np.sum(g ** 2)
    total_norm = np.sqrt(total_norm_sq)

    if total_norm > max_norm:
        scale = max_norm / (total_norm + 1e-8)  # epsilon avoids div-by-0
        for key in grads:
            grads[key] *= scale

    return grads


# ---------------------------------------------------------------------------
# Mini-batch / sequence generator
# ---------------------------------------------------------------------------

def sequence_batches(data_indices, seq_length):
    """
    Generator that yields consecutive (input, target) chunks from a
    long stream of character indices, for "truncated BPTT" style
    training: we chop a very long text into fixed-length windows of
    `seq_length` characters and train on each window independently,
    carrying the hidden state forward between windows (handled in
    train.py).

    For a window of characters c[t], c[t+1], ..., c[t+seq_length]:
        inputs  = c[t]   ... c[t+seq_length-1]   (what the model sees)
        targets = c[t+1] ... c[t+seq_length]      (what it should predict)

    i.e. targets are just inputs shifted one character to the right -
    classic "predict the next character" self-supervised training.
    """
    n = len(data_indices)
    for start in range(0, n - seq_length - 1, seq_length):
        inputs = data_indices[start: start + seq_length]
        targets = data_indices[start + 1: start + seq_length + 1]
        yield inputs, targets


# ---------------------------------------------------------------------------
# Saving / loading model parameters
# ---------------------------------------------------------------------------

def save_model(params, char_to_idx, idx_to_char, path):
    """
    Persist trained parameters + vocabulary to a single pickle file so
    predict.py can later reload the exact same model.
    """
    with open(path, "wb") as f:
        pickle.dump({
            "params": params,
            "char_to_idx": char_to_idx,
            "idx_to_char": idx_to_char,
        }, f)


def load_model(path):
    """Load parameters + vocabulary previously saved with save_model()."""
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data["params"], data["char_to_idx"], data["idx_to_char"]
