"""
activations.py
================
All the non-linear activation functions used by the LSTM, implemented
by hand with plain NumPy so you can see exactly what is happening
mathematically. Every function also has a companion "*_derivative"
function, because Backpropagation Through Time (BPTT) needs the local
derivative of each activation to build up the chain rule.

Notation used throughout the project:
    x  -> raw pre-activation input to a neuron ("logit")
    y  -> the activation's output, i.e. y = f(x)
    dy -> upstream gradient dL/dy flowing back into this activation
    dx -> the gradient we need to hand further back, dL/dx

For every derivative function below we follow the convention
    derivative(y) -> f'(x) expressed in terms of y = f(x)
This is a very common trick: for sigmoid and tanh, f'(x) can be written
purely in terms of f(x), so we avoid recomputing x during the backward
pass and simply reuse the cached forward activation.
"""

import numpy as np


def sigmoid(x):
    """
    Logistic sigmoid: squashes any real number into (0, 1).

        sigmoid(x) = 1 / (1 + exp(-x))

    Used for the LSTM's forget/input/output "gates" because a gate
    value between 0 and 1 can be interpreted as "how much information
    to let through" (0 = block everything, 1 = let everything through).

    We clip x before exponentiating to avoid overflow warnings for very
    large negative numbers (exp(-x) would blow up to inf).
    """
    x = np.clip(x, -500, 500)  # numerical safety net
    return 1.0 / (1.0 + np.exp(-x))


def sigmoid_derivative(y):
    """
    Derivative of sigmoid, expressed in terms of the already-computed
    output y = sigmoid(x):

        d/dx sigmoid(x) = sigmoid(x) * (1 - sigmoid(x)) = y * (1 - y)
    """
    return y * (1.0 - y)


def tanh(x):
    """
    Hyperbolic tangent: squashes any real number into (-1, 1).

        tanh(x) = (exp(x) - exp(-x)) / (exp(x) + exp(-x))

    Used for the LSTM's candidate cell state and for squashing the
    cell state before the output gate is applied. Centered at 0 (unlike
    sigmoid), which tends to help gradients flow better.

    NumPy's own np.tanh is already numerically stable, so we simply
    delegate to it rather than re-deriving the exponential formula.
    """
    return np.tanh(x)


def tanh_derivative(y):
    """
    Derivative of tanh, expressed in terms of the output y = tanh(x):

        d/dx tanh(x) = 1 - tanh(x)^2 = 1 - y^2
    """
    return 1.0 - y * y


def softmax(x):
    """
    Converts a vector of raw scores ("logits") into a probability
    distribution that sums to 1. Used on the final output layer so we
    can interpret the network's output as "probability of each
    character in the vocabulary being the next character".

        softmax(x)_i = exp(x_i) / sum_j exp(x_j)

    We subtract the max value from x before exponentiating purely for
    numerical stability (this does not change the mathematical result,
    since softmax is invariant to adding/subtracting a constant from
    every entry, but it prevents exp() from overflowing).

    x can be a 1D vector (single example) or a 2D array of shape
    (vocab_size, batch_size) where softmax is applied independently to
    each column.
    """
    x_shifted = x - np.max(x, axis=0, keepdims=True)
    exp_x = np.exp(x_shifted)
    return exp_x / np.sum(exp_x, axis=0, keepdims=True)

# NOTE: We do not define a separate "softmax_derivative" function here.
# In practice, softmax is almost always paired with cross-entropy loss,
# and the combined derivative of that pair collapses into the very
# simple expression (predicted_probs - true_one_hot). That simplified
# gradient is computed directly in loss.py, which is more numerically
# stable and efficient than computing the full softmax Jacobian matrix.
