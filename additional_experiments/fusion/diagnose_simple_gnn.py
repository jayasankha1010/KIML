"""
Why do the anchor configurations not reproduce the published ordering?

The first run of run_simple_gnn.py gave DEE median ranks of

    ll only     4953.5      (published GNN    3002)
    hl only     4086.5      (published C-GNN  2141)
    ll+hl       4179        (published KI-GNN 1328.5)

The hl > ll part of the ordering IS reproduced. What is not is that combining
the two beats either alone - here it is indistinguishable from hl alone - and
every number is roughly twice the published rank.

Guessing at fixes costs a full 5-fold run each time, so this measures instead.
It trains ONE fold and reports the loss and the target median rank at epoch
checkpoints, which separates the two candidate explanations:

  undertrained     the curves are still improving at the final epoch, and the
                   782-dim concat row lags the 384-dim one simply because it
                   has more to fit
  oversmoothed     the curves flatten early at a poor value, and adding
                   features cannot help because message passing has already
                   collapsed the node representations

Single-fold scores are mildly optimistic - some targets sat in the training
fold as negatives - so do NOT quote these numbers. They are for comparing
configurations and epochs against each other, which is unaffected.

Usage:
    python additional_experiments/fusion/diagnose_simple_gnn.py
    python additional_experiments/fusion/diagnose_simple_gnn.py --no-residual
"""

import argparse
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_simple_gnn as G  # noqa: E402

CONFIGS = [("ll only", ["ll"]), ("hl only", ["hl"]), ("ll+hl concat", ["ll", "hl"])]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disease", default="dee")
    parser.add_argument("--epochs", type=int, default=1000)
    parser.add_argument("--every", type=int, default=100)
    parser.add_argument("--hidden", type=int, default=50)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--pos-weight", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--no-residual", action="store_true",
                        help="disable the skip connections, to isolate their effect")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    device = args.device
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"

    pos_file, tgt_file = G.DISEASES[args.disease]
    positives = G.read_genes(os.path.join(G.DATA, "diseases", pos_file))
    targets = G.read_genes(os.path.join(G.DATA, "diseases", tgt_file))

    blocks = {k: G.load_block(v) for k, v in G.FEATURE_FILES.items()}
    genes = sorted(set.intersection(*(set(b) for b in blocks.values())))
    index = {g: i for i, g in enumerate(genes)}
    adj, n_edges = G.build_adjacency(genes, index, device)

    is_pos = np.array([g in positives for g in genes])
    y = torch.tensor(is_pos.astype(np.float32), device=device)
    pos_idx = np.flatnonzero(is_pos)
    unl_idx = np.flatnonzero(~is_pos)

    print("device {}, {} genes, {:,} edges, {} positives".format(
        device, len(genes), n_edges, len(pos_idx)))
    print("residual connections: {}\n".format("off" if args.no_residual else "on"))

    # One fold: hold out a fifth of the unlabelled genes, train on the rest.
    rng = np.random.default_rng(args.seed)
    folds = np.array_split(rng.permutation(unl_idx), 5)
    train = np.concatenate([pos_idx] + [folds[j] for j in range(1, 5)])
    mask = torch.zeros(len(genes), dtype=torch.bool, device=device)
    mask[torch.tensor(train, device=device)] = True

    target_set = sorted(targets)

    for label, block_names in CONFIGS:
        mats = [np.vstack([blocks[b][g] for g in genes]) for b in block_names]
        dims = [m.shape[1] for m in mats]
        X = torch.tensor(np.hstack(mats), device=device)
        X = (X - X.mean(0)) / (X.std(0) + 1e-6)

        torch.manual_seed(args.seed)
        model = G.FusionGNN(dims, args.hidden, "concat", True).to(device)
        if args.no_residual:
            _strip_residual(model)
        opt = torch.optim.Adam(model.parameters(), lr=args.lr)
        w = torch.tensor([args.pos_weight], device=device)

        print("{}  ({} dims)".format(label, sum(dims)))
        print("  {:>7}{:>12}{:>14}".format("epoch", "loss", "median rank"))
        for epoch in range(1, args.epochs + 1):
            model.train()
            opt.zero_grad()
            out = model(X, adj)
            loss = F.binary_cross_entropy_with_logits(
                out[mask], y[mask], pos_weight=w)
            loss.backward()
            opt.step()

            if epoch % args.every == 0 or epoch == 1:
                model.eval()
                with torch.no_grad():
                    scores = torch.sigmoid(model(X, adj)).cpu().numpy()
                order = unl_idx[np.argsort(-scores[unl_idx], kind="stable")]
                rank_of = {genes[i]: r + 1 for r, i in enumerate(order)}
                hits = [rank_of[g] for g in target_set if g in rank_of]
                print("  {:>7}{:>12.4f}{:>14.1f}".format(
                    epoch, loss.item(), float(np.median(hits))))
        print()


def _strip_residual(model):
    """Monkeypatch forward back to the plain non-residual GCN."""
    def forward(x, adj, m=model):
        h = F.elu(m.fuse(x))
        h = F.elu(torch.sparse.mm(adj, m.mp1(h)))
        h = F.elu(torch.sparse.mm(adj, m.mp2(h)))
        return m.head(h).squeeze(-1)
    model.forward = forward


if __name__ == "__main__":
    main()
