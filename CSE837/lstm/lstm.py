"""
lstm.py
=======
The heart of this project: a Long Short-Term Memory (LSTM) network
implemented from first principles using only NumPy.

--------------------------------------------------------------------
1. WHY LSTMs EXIST
--------------------------------------------------------------------
Plain "vanilla" RNNs struggle to learn long-range dependencies because
gradients either vanish (shrink to ~0) or explode (blow up to huge
values) as they are propagated backward through many timesteps. LSTMs
solve this with a "cell state" that acts like a conveyor belt of
information, plus three learned "gates" that control what information
is added, removed, or read from that conveyor belt at each timestep.

--------------------------------------------------------------------
2. THE FOUR LSTM EQUATIONS (forward pass, at timestep t)
--------------------------------------------------------------------
Let x_t   = input vector at time t (one-hot encoded character)
    h_{t-1} = hidden state from the previous timestep
    z_t   = [x_t ; h_{t-1}]   (x_t and h_{t-1} stacked/concatenated)

Then, using learned weight matrices W* and biases b*:

    f_t = sigmoid(Wf . z_t + bf)      "forget gate"
    i_t = sigmoid(Wi . z_t + bi)      "input gate"
    o_t = sigmoid(Wo . z_t + bo)      "output gate"
    g_t = tanh(Wg . z_t + bg)         "candidate cell state"

    c_t = f_t * c_{t-1}  +  i_t * g_t     "new cell state"
    h_t = o_t * tanh(c_t)                 "new hidden state"

Interpretation of the gates (each is a vector of values in [0, 1],
one per hidden unit, acting as a per-unit "how much to let through"):
    f_t -> how much of the OLD cell state to KEEP   (forget gate)
    i_t -> how much of the NEW candidate to WRITE IN (input gate)
    o_t -> how much of the cell state to EXPOSE as the hidden state
           (output gate)

Finally, the hidden state is projected to a distribution over the
vocabulary for next-character prediction:

    y_t = Wy . h_t + by
    p_t = softmax(y_t)

--------------------------------------------------------------------
3. BACKPROPAGATION THROUGH TIME (BPTT)
--------------------------------------------------------------------
Because the same weights are reused at every timestep, training an
LSTM means unrolling it across all T timesteps of a sequence, computing
the loss at every step, and then propagating gradients backward from
the LAST timestep to the FIRST, accumulating gradient contributions
for the (shared) weight matrices along the way. Two gradient "rivers"
flow backward between timesteps: dh_next (into h_{t-1}) and dc_next
(into c_{t-1}) - this is what lets errors made at timestep t influence
how the network handled much earlier timesteps.

All the calculus for this is implemented step by step in `backward()`
below, with comments tracing every derivative back to the equations
above.
"""

import numpy as np
from activations import sigmoid, sigmoid_derivative, tanh, tanh_derivative, softmax
from loss import cross_entropy_loss, cross_entropy_loss_derivative
from utils import xavier_init, clip_gradients


class LSTM:
    """
    A single-layer character-level LSTM language model.

    Architecture:
        input (one-hot, vocab_size)
            -> LSTM cell (hidden_size)
            -> Linear output layer (vocab_size)
            -> softmax
    """

    def __init__(self, vocab_size, hidden_size, seed=42):
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size

        z_size = hidden_size + vocab_size  # size of concatenated [h, x]

        # --------------------------------------------------------
        # Parameter initialization.
        # Each gate has its own weight matrix of shape
        # (hidden_size, z_size) so it can read from both the new
        # input x_t and the previous hidden state h_{t-1}, plus a
        # bias vector of shape (hidden_size, 1).
        # --------------------------------------------------------
        self.params = {}
        rng_seed = seed
        for gate_name in ["f", "i", "o", "g"]:
            self.params[f"W{gate_name}"] = xavier_init(hidden_size, z_size, seed=rng_seed)
            self.params[f"b{gate_name}"] = np.zeros((hidden_size, 1))
            rng_seed += 1  # vary seed per matrix so gates don't start identical

        # Output projection layer: hidden_size -> vocab_size
        self.params["Wy"] = xavier_init(vocab_size, hidden_size, seed=rng_seed)
        self.params["by"] = np.zeros((vocab_size, 1))

    # =====================================================================
    # FORWARD PASS
    # =====================================================================
    def forward(self, input_indices, h_prev, c_prev):
        """
        Run the LSTM forward over an entire sequence of input character
        indices, one timestep at a time, caching every intermediate
        value we will need later during backpropagation.

        Parameters
        ----------
        input_indices : list[int] of length T - the input characters
                        (as vocabulary indices) for this training chunk
        h_prev, c_prev : np.ndarray of shape (hidden_size, 1) - the
                        hidden/cell state carried over from the previous
                        chunk (truncated BPTT)

        Returns
        -------
        caches : list of dicts, one per timestep, holding every value
                 needed for backward()
        probs  : list of np.ndarray, softmax probability distribution
                 output at every timestep
        h_prev, c_prev : the final hidden/cell state (to carry into the
                 next chunk)
        """
        caches = []
        probs = []

        h, c = h_prev, c_prev

        for t, idx in enumerate(input_indices):
            # ---- build one-hot input vector for this timestep ----
            x = np.zeros((self.vocab_size, 1))
            x[idx, 0] = 1.0

            h, c = h, c  # rename for clarity below
            h_prev_t, c_prev_t = h, c  # snapshot of state BEFORE this step

            # ---- concatenate input and previous hidden state ----
            z = np.vstack((h_prev_t, x))  # shape: (hidden_size + vocab_size, 1)

            # ---- the four gate computations ----
            f = sigmoid(self.params["Wf"] @ z + self.params["bf"])
            i = sigmoid(self.params["Wi"] @ z + self.params["bi"])
            o = sigmoid(self.params["Wo"] @ z + self.params["bo"])
            g = tanh(self.params["Wg"] @ z + self.params["bg"])

            # ---- new cell state and hidden state ----
            c = f * c_prev_t + i * g
            tanh_c = tanh(c)
            h = o * tanh_c

            # ---- output projection + softmax ----
            y = self.params["Wy"] @ h + self.params["by"]
            p = softmax(y)

            # ---- cache everything backward() will need ----
            caches.append({
                "x": x, "z": z,
                "f": f, "i": i, "o": o, "g": g,
                "c": c, "c_prev": c_prev_t,
                "tanh_c": tanh_c,
                "h": h, "h_prev": h_prev_t,
            })
            probs.append(p)

        return caches, probs, h, c

    # =====================================================================
    # BACKWARD PASS  (Backpropagation Through Time)
    # =====================================================================
    def backward(self, input_indices, target_indices, caches, probs):
        """
        Compute gradients of the total sequence loss with respect to
        every parameter, by propagating derivatives backward from the
        LAST timestep to the FIRST (hence "through time").

        Parameters
        ----------
        input_indices  : list[int] - inputs fed at each timestep (unused
                          directly here since it's baked into caches,
                          kept for interface symmetry/clarity)
        target_indices : list[int] - the TRUE next-character index at
                          each timestep (what the loss is computed against)
        caches         : list of per-timestep caches from forward()
        probs          : list of per-timestep softmax outputs from forward()

        Returns
        -------
        grads     : dict[str, np.ndarray] - gradient for every parameter,
                    same keys/shapes as self.params
        total_loss: float - summed cross-entropy loss over the sequence
        """
        T = len(input_indices)

        # ---- allocate gradient accumulators (same shapes as params) ----
        grads = {k: np.zeros_like(v) for k, v in self.params.items()}

        # ---- these two "rivers" carry gradient information backward
        #      between consecutive timesteps ----
        dh_next = np.zeros((self.hidden_size, 1))  # dL/dh_t contribution from t+1
        dc_next = np.zeros((self.hidden_size, 1))  # dL/dc_t contribution from t+1

        total_loss = 0.0

        # ---- iterate backward: t = T-1, T-2, ..., 0 ----
        for t in reversed(range(T)):
            cache = caches[t]
            p = probs[t]
            target = target_indices[t]

            total_loss += cross_entropy_loss(p, target)

            # =========================================================
            # STEP 1: gradient of loss w.r.t. output logits y_t
            #         dL/dy = p - one_hot(target)   (softmax+CE identity)
            # =========================================================
            dy = cross_entropy_loss_derivative(p, target)  # shape (vocab, 1)

            # =========================================================
            # STEP 2: gradient into the output projection layer
            #         y = Wy . h + by
            #   dL/dWy = dy . h^T         dL/dby = dy
            #   dL/dh (from THIS timestep's output) = Wy^T . dy
            # =========================================================
            grads["Wy"] += dy @ cache["h"].T
            grads["by"] += dy
            dh = self.params["Wy"].T @ dy  # contribution to dL/dh_t from the output layer

            # Add the gradient flowing in from the FUTURE timestep
            # (t+1)'s dependence on h_t, accumulated in dh_next.
            dh += dh_next

            # =========================================================
            # STEP 3: gradient w.r.t. cell state c_t
            #         h_t = o_t * tanh(c_t)
            #   dL/d(tanh(c_t)) = dh * o_t
            #   dL/dc_t (direct path) = dh * o_t * (1 - tanh(c_t)^2)
            # plus the gradient flowing in from the future timestep's
            # dependence on c_t (since c_{t+1} = f_{t+1}*c_t + ...),
            # captured in dc_next.
            # =========================================================
            do = dh * cache["tanh_c"]                       # dL/do_t (pre-derivative)
            dc = dh * cache["o"] * tanh_derivative(cache["tanh_c"])
            dc += dc_next

            # =========================================================
            # STEP 4: gradients w.r.t. the gates f, i, g
            #   c_t = f_t * c_{t-1} + i_t * g_t
            #   dL/df_t = dc * c_{t-1}
            #   dL/di_t = dc * g_t
            #   dL/dg_t = dc * i_t
            # =========================================================
            df = dc * cache["c_prev"]
            di = dc * cache["g"]
            dg = dc * cache["i"]

            # =========================================================
            # STEP 5: push each gate's gradient through its own
            # activation function to get the gradient w.r.t. the
            # PRE-activation values (the raw W.z + b logits), because
            # that is what we need to compute dW and db.
            #   f, i, o use sigmoid ; g uses tanh
            # =========================================================
            df_pre = df * sigmoid_derivative(cache["f"])
            di_pre = di * sigmoid_derivative(cache["i"])
            do_pre = do * sigmoid_derivative(cache["o"])
            dg_pre = dg * tanh_derivative(cache["g"])

            # =========================================================
            # STEP 6: gradients w.r.t. each gate's weight matrix/bias.
            # Every gate computes: gate_pre = W_gate . z + b_gate
            #   dL/dW_gate = gate_pre_grad . z^T
            #   dL/db_gate = gate_pre_grad
            # =========================================================
            z = cache["z"]
            grads["Wf"] += df_pre @ z.T
            grads["bf"] += df_pre
            grads["Wi"] += di_pre @ z.T
            grads["bi"] += di_pre
            grads["Wo"] += do_pre @ z.T
            grads["bo"] += do_pre
            grads["Wg"] += dg_pre @ z.T
            grads["bg"] += dg_pre

            # =========================================================
            # STEP 7: propagate gradient back into z = [h_{t-1}; x_t],
            # then slice out just the h_{t-1} portion (we don't need
            # gradients w.r.t. the one-hot input x_t itself, since the
            # input is fixed data, not a learnable parameter). This
            # becomes dh_next for the PREVIOUS iteration (i.e. timestep
            # t-1's "future gradient").
            # =========================================================
            dz = (self.params["Wf"].T @ df_pre
                  + self.params["Wi"].T @ di_pre
                  + self.params["Wo"].T @ do_pre
                  + self.params["Wg"].T @ dg_pre)

            dh_next = dz[:self.hidden_size, :]  # first hidden_size rows are the h_{t-1} part

            # =========================================================
            # STEP 8: gradient w.r.t. c_{t-1}, needed by the previous
            # (earlier) timestep. Since c_t = f_t * c_{t-1} + i_t * g_t:
            #   dL/dc_{t-1} = dc * f_t
            # =========================================================
            dc_next = dc * cache["f"]

        return grads, total_loss

    # =====================================================================
    # PARAMETER UPDATE  (plain Stochastic Gradient Descent)
    # =====================================================================
    def update_params(self, grads, learning_rate):
        """
        Vanilla SGD update rule, applied independently to every
        parameter tensor:

            theta <- theta - learning_rate * dL/dtheta

        Gradients are assumed to have ALREADY been clipped (see
        utils.clip_gradients) before this is called, to prevent
        exploding updates from destabilizing training.
        """
        for key in self.params:
            self.params[key] -= learning_rate * grads[key]

    # =====================================================================
    # SAMPLING / GENERATION (used at inference time by predict.py)
    # =====================================================================
    def sample(self, seed_index, h_prev, c_prev, n_chars, temperature=1.0):
        """
        Generate `n_chars` new character indices autoregressively:
        feed the model's own previous prediction back in as the next
        input, one character at a time (this is exactly how you use a
        trained language model to generate novel text).

        Parameters
        ----------
        seed_index  : int - index of the character to "kick off" generation
        h_prev, c_prev : starting hidden/cell state (often zeros, or
                       carried over from a prompt that was fed through
                       forward() first)
        n_chars     : how many characters to generate
        temperature : float > 0 - controls randomness of sampling.
                      temperature < 1 -> more confident/conservative,
                      temperature > 1 -> more random/creative.
                      Implemented by rescaling logits before softmax:
                      softmax(logits / temperature).

        Returns
        -------
        list[int] of generated character indices (length n_chars)
        """
        h, c = h_prev, c_prev
        idx = seed_index
        generated = []

        for _ in range(n_chars):
            x = np.zeros((self.vocab_size, 1))
            x[idx, 0] = 1.0
            z = np.vstack((h, x))

            f = sigmoid(self.params["Wf"] @ z + self.params["bf"])
            i = sigmoid(self.params["Wi"] @ z + self.params["bi"])
            o = sigmoid(self.params["Wo"] @ z + self.params["bo"])
            g = tanh(self.params["Wg"] @ z + self.params["bg"])

            c = f * c + i * g
            h = o * tanh(c)

            y = self.params["Wy"] @ h + self.params["by"]
            p = softmax(y / max(temperature, 1e-8))

            # sample the next character index from the probability
            # distribution p (rather than always greedily picking the
            # single most likely character, which tends to produce
            # repetitive/boring text)
            idx = np.random.choice(range(self.vocab_size), p=p.ravel())
            generated.append(idx)

        return generated
