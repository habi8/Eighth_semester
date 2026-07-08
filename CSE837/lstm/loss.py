"""
loss.py
=======
Loss function used to train the character-level language model:
softmax + categorical cross-entropy.

At every timestep the LSTM outputs a probability distribution over the
vocabulary (via softmax). We compare that distribution to the true
"next character" (represented as a one-hot vector) using cross-entropy
loss, which measures how "surprised" the model is by the true answer.
"""

import numpy as np


def cross_entropy_loss(probs, target_index):
    """
    Cross-entropy loss for a single timestep.

        L = -log(probs[target_index])

    Parameters
    ----------
    probs        : np.ndarray of shape (vocab_size, 1) - predicted
                   probability distribution from softmax
    target_index : int - index of the true next character

    Returns
    -------
    scalar loss value (float)

    Intuition: if the model assigns high probability to the correct
    character, -log(p) is close to 0 (low loss). If the model assigns
    low probability to the correct character, -log(p) is large
    (high loss). This heavily penalizes confident-but-wrong
    predictions.
    """
    # Small epsilon prevents log(0) = -inf if the model ever outputs
    # an exact 0 probability (can happen due to floating point underflow).
    p = probs[target_index, 0]
    return -np.log(p + 1e-12)


def cross_entropy_loss_derivative(probs, target_index):
    """
    Gradient of the combined softmax + cross-entropy loss with respect
    to the *pre-softmax logits* z (not the post-softmax probabilities!).

    This is one of the most useful identities in deep learning: even
    though softmax's own Jacobian is a full (vocab_size x vocab_size)
    matrix, and cross-entropy's derivative w.r.t. probabilities
    involves a division, the two combine and simplify beautifully to:

        dL/dz = probs - one_hot(target_index)

    Derivation sketch:
        L = -log(probs[target])
        probs[i] = exp(z_i) / sum_j exp(z_j)
        => dL/dz_i = probs[i] - 1{i == target}

    Parameters
    ----------
    probs        : np.ndarray of shape (vocab_size, 1) - softmax output
    target_index : int - index of the true next character

    Returns
    -------
    np.ndarray of shape (vocab_size, 1) - gradient dL/dz to be
    backpropagated into the output layer.
    """
    dz = probs.copy()
    dz[target_index, 0] -= 1.0
    return dz
