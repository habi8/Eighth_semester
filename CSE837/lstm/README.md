# LSTM from Scratch (Pure NumPy)

An educational, dependency-free implementation of a **Long Short-Term
Memory (LSTM)** network, trained as a **character-level language
model**. No PyTorch, no TensorFlow, no autograd — every forward
equation, every backward gradient, and the SGD update rule are written
out explicitly in NumPy so you can read the code line-by-line
alongside the math.

This is meant to be *read*, not just run. Every file is full of
comments explaining **what** each line computes and **why**.

## What it does

The model learns to predict the next character in a piece of text,
one character at a time. Once trained, it can generate new text by
repeatedly feeding its own predictions back in as the next input
("autoregressive sampling").

## File structure

| File             | Contents |
|------------------|----------|
| `activations.py` | `sigmoid`, `tanh`, `softmax`, and their derivatives |
| `utils.py`       | vocabulary building, one-hot encoding, Xavier init, gradient clipping, batching, save/load |
| `loss.py`        | softmax cross-entropy loss and its (simplified) gradient |
| `lstm.py`        | the `LSTM` class: forward pass, BPTT backward pass, SGD update, sampling |
| `train.py`       | training script (truncated BPTT + SGD + gradient clipping) |
| `predict.py`     | loads a trained model and generates text |
| `README.md`      | this file |

## The math, briefly

At each timestep `t`, given input `x_t` and previous hidden/cell state
`(h_{t-1}, c_{t-1})`, with `z_t = [h_{t-1}; x_t]`:

```
f_t = sigmoid(Wf . z_t + bf)     # forget gate  — how much of c_{t-1} to keep
i_t = sigmoid(Wi . z_t + bi)     # input gate   — how much of g_t to write in
o_t = sigmoid(Wo . z_t + bo)     # output gate  — how much of c_t to expose
g_t = tanh(Wg . z_t + bg)        # candidate cell state

c_t = f_t * c_{t-1} + i_t * g_t  # new cell state ("memory")
h_t = o_t * tanh(c_t)            # new hidden state

y_t = Wy . h_t + by              # project to vocabulary logits
p_t = softmax(y_t)               # predicted next-character distribution
```

Training uses **cross-entropy loss** at every timestep, and gradients
are computed with **Backpropagation Through Time (BPTT)**: the
network is unrolled across a chunk of timesteps, and gradients flow
backward from the last timestep to the first, accumulating
contributions to the (shared, reused-at-every-step) weight matrices.
Two gradient "rivers" — `dh_next` and `dc_next` — carry information
from timestep `t+1` back into timestep `t`.

Because RNN/LSTM gradients can explode over long sequences, gradients
are **clipped by global L2 norm** before every parameter update (see
`utils.clip_gradients`).

Training uses **truncated BPTT**: long text is chopped into fixed-length
chunks (`--seq_length`), gradients only flow backward within a chunk,
but the hidden/cell state is carried *forward* between chunks so the
model still has a "memory" of everything before the current chunk.

## Quick start

```bash
# 1. Train on the tiny built-in demo corpus (just to sanity-check everything works)
python train.py --epochs 5 --hidden_size 64 --save_path model.pkl

# 2. Train on your own text file
python train.py --data mytext.txt --hidden_size 128 --seq_length 25 \
                 --learning_rate 0.1 --epochs 20 --save_path model.pkl

# 3. Generate text from the trained model
python predict.py --model model.pkl --seed_text "Once upon a time" \
                   --length 300 --temperature 0.8
```

### Key hyperparameters

- `--hidden_size`: number of LSTM hidden units (model capacity)
- `--seq_length`: truncated-BPTT chunk length (how far gradients propagate back)
- `--learning_rate`: SGD step size
- `--clip_norm`: max global gradient norm before clipping kicks in
- `--temperature` (predict.py): sampling randomness; lower = more conservative/repetitive, higher = more random/creative

## Verifying correctness

Because this is hand-derived calculus, it's easy to make a sign error
or transpose mistake. The gradients in `lstm.py` were verified against
**numerical gradient checking** (finite differences: comparing
`(loss(theta+eps) - loss(theta-eps)) / (2*eps)` against the analytic
gradient for many parameters) with relative errors on the order of
`1e-7` to `1e-10` — essentially floating-point noise, confirming the
backward pass is mathematically correct.

## Design choices / limitations (by design, for clarity)

- **Single-layer LSTM only** — no stacking, no bidirectionality. Adding
  more layers is a natural extension once you understand this version.
- **Plain SGD**, not Adam/RMSprop — simpler to read and reason about.
  Swapping in a fancier optimizer just means replacing
  `update_params()`.
- **Character-level, not word-level** — keeps the vocabulary small and
  avoids needing a tokenizer, so the whole pipeline stays simple.
- **Batch size of 1** (single sequence unrolled at a time) — makes the
  BPTT code easier to follow. Extending to mini-batches would mean
  adding a batch axis to every array.
- No dropout, layer norm, or other regularization — kept minimal on
  purpose for a first read-through of the core algorithm.

## Suggested exercises

1. Add a second stacked LSTM layer.
2. Replace SGD with Adam (you'll need to track first/second moment
   estimates per parameter).
3. Switch from truncated BPTT to full BPTT on short sequences and
   compare training stability.
4. Implement mini-batching (process several sequences in parallel).
5. Add dropout on the hidden state between timesteps.
