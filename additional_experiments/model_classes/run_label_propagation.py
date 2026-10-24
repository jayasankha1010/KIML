"""
Label propagation as a fifth model class (Reviewer 1, comment 3).

R1.3 names three methods specifically - XGBoost, MLPs, label propagation. The
first two are covered by run_model_classes.py (gradient boosting standing in for
XGBoost); this closes the third, so no method the reviewer named is left
untested.

WHY THE GRAPH IS BUILT FROM FEATURES. Label propagation is a graph method, but
R1.3 does not ask "does a graph method work". It asks whether the reported
benefit of knowledge inclusion survives a change of model class. Propagating
over the fixed KIML knowledge graph would not involve the feature sets at all,
so it could not answer that question - and that configuration is already
covered, as row 7 of the fusion ablation table. Instead the affinity graph is
derived from the features themselves: a cosine kNN graph built separately from
LL, from HL, and from LL+HL. The feature sets then enter exactly as they do for
every other model class, and the three rows are comparable.

Zhou et al. label spreading:  F <- alpha S F + (1 - alpha) Y,
with S the symmetrically normalised affinity and Y the seed matrix.

POSITIVE-UNLABELLED HANDLING. The other model classes need out-of-fold scoring
because they must invent negatives. Label propagation does not: only positives
are seeded, every other gene starts at zero and receives score purely by
proximity. No gene is ever used as a negative, so the ranking is honest without
folds. That is a property of the method, not a shortcut - n_folds is reported
as 0 to make the difference visible rather than silently incomparable.

Usage:
    python additional_experiments/model_classes/run_label_propagation.py
    python additional_experiments/model_classes/run_label_propagation.py --diseases dee cp
"""

import argparse
import csv
import os
import sys
import time

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
sys.path.insert(0, HERE)
from revision_analysis import bootstrap, paired_bootstrap  # noqa: E402
from run_model_classes import DISEASES, FEATURE_SETS, DATA, load_matrix, read_genes  # noqa: E402


def knn_affinity(X, k, device, chunk=2048):
    """Sparse symmetric cosine kNN affinity over the rows of X.

    Columns are standardised before the rows are L2-normalised: LL is cortical
    expression and HL is 384-dim embeddings, and without standardising, whichever
    block has the larger raw scale would dominate the cosine and the LL+HL row
    would silently be a single-block result.
    """
    X = torch.as_tensor(X, dtype=torch.float32, device=device)
    X = (X - X.mean(0)) / (X.std(0) + 1e-6)
    X = X / (X.norm(dim=1, keepdim=True) + 1e-12)

    n = X.shape[0]
    rows, cols, vals = [], [], []
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        sim = X[start:stop] @ X.T
        # Drop self-similarity before taking neighbours.
        sim[torch.arange(stop - start, device=device),
            torch.arange(start, stop, device=device)] = -2.0
        top_v, top_i = torch.topk(sim, k, dim=1)
        top_v = top_v.clamp_min(0)
        src = torch.arange(start, stop, device=device).unsqueeze(1).expand(-1, k)
        rows.append(src.reshape(-1))
        cols.append(top_i.reshape(-1))
        vals.append(top_v.reshape(-1))

    r = torch.cat(rows)
    c = torch.cat(cols)
    v = torch.cat(vals)
    # Symmetrise: kNN is directional, label spreading needs it undirected.
    idx = torch.stack([torch.cat([r, c]), torch.cat([c, r])])
    val = torch.cat([v, v])

    deg = torch.zeros(n, device=device).scatter_add_(0, idx[0], val)
    norm = (deg + 1e-12).pow(-0.5)
    val = norm[idx[0]] * val * norm[idx[1]]
    return torch.sparse_coo_tensor(idx, val, (n, n)).coalesce()


def label_spread(S, seeds, alpha, iters):
    f = seeds.clone()
    for _ in range(iters):
        f = alpha * torch.sparse.mm(S, f.unsqueeze(1)).squeeze(1) + (1 - alpha) * seeds
    return f


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diseases", nargs="*", default=["dee"],
                        help="subset of {}, or 'all'".format(sorted(DISEASES)))
    parser.add_argument("-k", "--neighbours", type=int, default=15)
    parser.add_argument("--alpha", type=float, default=0.8)
    parser.add_argument("--iters", type=int, default=50)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--device", default="auto")
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "model_class_label_propagation.tsv"))
    args = parser.parse_args()

    if args.diseases == ["all"]:
        args.diseases = sorted(DISEASES)

    device = args.device
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    print("device: {}   k={}  alpha={}".format(device, args.neighbours, args.alpha))

    loaded = {name: load_matrix(paths) for name, paths in FEATURE_SETS.items()}

    # The affinity graph depends only on the features, so build each once and
    # reuse it across diseases - it is by far the expensive part.
    affinity = {}
    for name, (genes, X) in loaded.items():
        started = time.time()
        affinity[name] = knn_affinity(X, args.neighbours, device)
        print("  {:22} {} genes x {} dims  ({:.0f}s)".format(
            name, len(genes), X.shape[1], time.time() - started))

    results = []
    contrasts = []
    print("\n{:24}{:22}{:>8}{:>10}  {}".format(
        "disease", "features", "targets", "median", "95% CI"))
    print("-" * 80)

    for disease in args.diseases:
        pos_file, tgt_file = DISEASES[disease]
        positives = read_genes(os.path.join(DATA, "diseases", pos_file))
        targets = read_genes(os.path.join(DATA, "diseases", tgt_file))
        ranks_by_features, universe_by_features = {}, {}

        for name, (genes, _) in loaded.items():
            is_pos = np.array([g in positives for g in genes])
            seeds = torch.tensor(is_pos.astype(np.float32), device=device)
            scores = label_spread(affinity[name], seeds,
                                  args.alpha, args.iters).cpu().numpy()

            unl = np.flatnonzero(~is_pos)
            order = unl[np.argsort(-scores[unl], kind="stable")]
            rank_of = {genes[i]: r + 1 for r, i in enumerate(order)}
            hit_genes = [g for g in sorted(targets) if g in rank_of]
            hits = [rank_of[g] for g in hit_genes]
            ranks_by_features[name] = {g: rank_of[g] for g in hit_genes}
            universe_by_features[name] = len(order)

            point, bounds = bootstrap(hits, len(order), args.n_boot, args.seed)
            record = {"disease": disease, "model": "Label propagation",
                      "features": name, "n_targets": len(hits),
                      "universe_size": len(order), "n_folds": 0,
                      "n_boot": args.n_boot}
            for key, value in point.items():
                record[key] = round(value, 4)
                if key in bounds:
                    record[key + "_lo"] = round(bounds[key][0], 4)
                    record[key + "_hi"] = round(bounds[key][1], 4)
            results.append(record)

            ci = bounds.get("median_rank_unseen")
            print("{:24}{:22}{:>8}{:>10}  {}".format(
                disease, name, len(hits),
                "{:g}".format(point["median_rank_unseen"]),
                "[{:g}, {:g}]".format(*ci) if ci else "-"))

        # Paired, because every feature set ranks the same target genes for this
        # disease. Comparing the marginal intervals printed above would be the
        # wrong test and would miss real differences.
        for a, b in [("LL+HL (KIML)", "LL (expression)"),
                     ("HL (PubMed)", "LL (expression)")]:
            if a not in ranks_by_features or b not in ranks_by_features:
                continue
            out, n = paired_bootstrap(
                ranks_by_features[a], ranks_by_features[b],
                universe_by_features[a], universe_by_features[b],
                args.n_boot, args.seed)
            if not out:
                continue
            record = {"disease": disease, "model": "Label propagation",
                      "A": a, "B": b, "n_shared_targets": n}
            for key, (diff, lo, hi, sig) in out.items():
                record[key] = round(diff, 4)
                record[key + "_lo"] = round(lo, 4)
                record[key + "_hi"] = round(hi, 4)
                record[key + "_significant"] = sig
            contrasts.append(record)

    if contrasts:
        print("\nPaired contrasts (negative = A ranks targets higher)")
        print("{:24}{:28}{:>22}{:>6}".format(
            "disease", "contrast", "difference [95% CI]", "sig"))
        print("-" * 80)
        for r in contrasts:
            d = r["median_rank_unseen"]
            lo, hi = r["median_rank_unseen_lo"], r["median_rank_unseen_hi"]
            label = "KI vs LL" if r["A"].startswith("LL+HL") else "HL vs LL"
            print("{:24}{:28}{:>22}{:>6}".format(
                r["disease"], label,
                "{:+.0f} [{:+.0f}, {:+.0f}]".format(d, lo, hi),
                "yes" if r["median_rank_unseen_significant"] else "no"))

        cols = []
        for r in contrasts:
            for k in r:
                if k not in cols:
                    cols.append(k)
        contrast_path = args.out.replace(".tsv", "_contrasts.tsv")
        with open(contrast_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
            writer.writeheader()
            writer.writerows(contrasts)
        print("\nWrote {} contrasts -> {}".format(len(contrasts), contrast_path))

    columns = []
    for record in results:
        for key in record:
            if key not in columns:
                columns.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("\nWrote {} rows -> {}".format(len(results), args.out))


if __name__ == "__main__":
    main()
