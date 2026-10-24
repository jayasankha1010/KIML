"""
A minimal GNN for the remaining R1.5 ablations (Reviewer 1, comment 5).

Three of the five sub-ablations R1.5 asks for are not answerable by rearranging
existing results:

  ii)  node features only versus knowledge graph only
  iii) literature SEMANTICS versus simple article COUNT, as a node feature
  iv)  plain concatenation versus a learned fusion of the two feature sets

Rather than modify SPEOS - whose architecture is on the path of every result
already produced - this is a deliberately small GCN in which exactly one thing
varies at a time. That is what makes an ablation table readable, and it runs on
a laptop in minutes instead of queueing.

WHAT THIS IS NOT. It is not KI-GNN: no FiLM, no multi-relational edges, no
nested cross-validation. Absolute numbers will not match Table 1 and should not
be compared against it. The comparison here is internal, between rows, with
everything else held fixed - which is precisely what R1.5 asks for. Rows 1-3 of
the suggested run are reference configurations; if they do not order
KI-GNN > C-GNN > GNN the way the published runs do, the ablation rows below them
are not yet interpretable.

Protocol matches the rest of the revision: positive-unlabelled k-fold out-of-fold
scoring (every gene ranked by a model that never saw it as a negative), and
metrics and bootstrap imported from revision_analysis so definitions cannot
drift.

Usage:
    python additional_experiments/fusion/run_simple_gnn.py --preset all
"""

import argparse
import csv
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
from revision_analysis import bootstrap  # noqa: E402

DATA = os.path.join(ROOT, "data", "kiml_data")
TEXT = os.path.join(ROOT, "additional_experiments", "text_representations")

FEATURE_FILES = {
    "ll": [os.path.join(DATA, "ahbd", "child_expression.txt"),
           os.path.join(DATA, "ahbd", "prebirth_expression.txt")],
    "hl": [os.path.join(DATA, "pubmed_embeddings",
                        "pubmed_embeddings_rearranged_2022_09.txt")],
    "count": [os.path.join(HERE, "pubmed_count_3d_2022_09_speos_symbols.txt")],
}

# Same two networks the published KI-GNN uses.
NETWORKS = [os.path.join(DATA, "networks", "network_pathway.txt"),
            os.path.join(DATA, "networks", "gene_gene_covaries.txt")]

DISEASES = {
    "dee": ("DEE-2022_09.txt", "DEE-2025_03_vs_2022_09.txt"),
    "cp": ("CP-2022-09.txt", "CP-2025_06_vs_2022_09.txt"),
}

# (name, feature blocks, graph, fusion). Blocks are fused pairwise when the
# fusion mode is not "concat"; "random" means uninformative node features, which
# is how the graph-only row is constructed.
PRESETS = [
    ("1_ll_kg",            ["ll"],           "kg",   "concat"),
    ("2_hl_kg",            ["hl"],           "kg",   "concat"),
    ("3_ll+hl_kg_concat",  ["ll", "hl"],     "kg",   "concat"),
    ("4_ll+hl_kg_sum",     ["ll", "hl"],     "kg",   "sum"),
    ("5_ll+hl_kg_gated",   ["ll", "hl"],     "kg",   "gated"),
    ("6_ll+hl_nograph",    ["ll", "hl"],     "none", "concat"),
    ("7_random_kg",        ["random"],       "kg",   "concat"),
    ("8_ll+count_kg",      ["ll", "count"],  "kg",   "concat"),
    ("9_count_kg",         ["count"],        "kg",   "concat"),
]


def read_genes(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def load_block(paths):
    """gene -> concatenated vector, for one logical feature block."""
    tables = []
    for path in paths:
        values = {}
        with open(path) as handle:
            for line in handle:
                parts = line.split()
                if len(parts) > 1:
                    values[parts[0]] = np.asarray(parts[1:], dtype=np.float32)
        tables.append(values)
    genes = set.intersection(*(set(t) for t in tables))
    return {g: np.concatenate([t[g] for t in tables]) for g in genes}


def build_adjacency(genes, index, device):
    """Symmetric-normalised sparse adjacency with self-loops: D^-1/2 (A+I) D^-1/2."""
    seen = set()
    rows, cols = [], []
    for path in NETWORKS:
        with open(path) as handle:
            next(handle, None)
            for line in handle:
                parts = line.split()
                if len(parts) < 2:
                    continue
                a, b = parts[0], parts[1]
                if a == b or a not in index or b not in index:
                    continue
                key = (a, b) if a < b else (b, a)
                if key in seen:
                    continue
                seen.add(key)
                i, j = index[a], index[b]
                rows += [i, j]
                cols += [j, i]
    n = len(genes)
    # self-loops
    rows += list(range(n))
    cols += list(range(n))

    idx = torch.tensor([rows, cols], dtype=torch.long)
    val = torch.ones(idx.shape[1], dtype=torch.float32)
    deg = torch.zeros(n, dtype=torch.float32).scatter_add_(0, idx[0], val)
    norm = deg.pow(-0.5)
    val = norm[idx[0]] * val * norm[idx[1]]
    return torch.sparse_coo_tensor(idx, val, (n, n)).coalesce().to(device), len(seen)


class FusionGNN(nn.Module):
    """2-layer GCN. The only thing that varies between ablations is how the
    feature blocks are combined before message passing."""

    def __init__(self, dims, hidden, fusion, use_graph, dropout=0.5):
        super().__init__()
        self.fusion = fusion if len(dims) > 1 else "concat"
        self.use_graph = use_graph
        self.dropout = dropout
        self.splits = np.cumsum([0] + list(dims))

        if self.fusion == "concat":
            self.proj = nn.ModuleList([nn.Linear(sum(dims), hidden)])
        else:
            # Project each block to a shared width, then combine additively.
            self.proj = nn.ModuleList([nn.Linear(d, hidden) for d in dims])
            if self.fusion == "gated":
                self.gate = nn.Parameter(torch.zeros(len(dims)))

        self.mp1 = nn.Linear(hidden, hidden)
        self.mp2 = nn.Linear(hidden, hidden)
        self.head = nn.Sequential(nn.Linear(hidden, hidden), nn.ELU(),
                                  nn.Linear(hidden, 1))

    def fuse(self, x):
        if self.fusion == "concat":
            return self.proj[0](x)
        parts = [self.proj[i](x[:, self.splits[i]:self.splits[i + 1]])
                 for i in range(len(self.proj))]
        if self.fusion == "gated":
            w = torch.softmax(self.gate, dim=0)
            return sum(w[i] * p for i, p in enumerate(parts))
        return sum(parts)

    def forward(self, x, adj):
        # Dropout on the input matters more than usual here: with 384-dim
        # PubMed embeddings the model can otherwise drive training loss to
        # ~1e-4, memorising the 736 positives outright (see
        # diagnose_simple_gnn.py). Expression features cannot memorise, so
        # without this the comparison between feature sets is really a
        # comparison of how easily each one overfits.
        x = F.dropout(x, self.dropout, self.training)
        h = F.elu(self.fuse(x))
        h = F.dropout(h, self.dropout, self.training)
        if self.use_graph:
            # Residual around each message-passing step. The pathway network has
            # mean degree ~1184, so plain neighbour averaging oversmooths: after
            # two hops every node's representation collapses toward the graph
            # mean and the ranking goes flat. SPEOS avoids this because FiLM
            # modulates messages rather than averaging them. Keeping the node's
            # own representation preserves the identity the ranking depends on.
            h = h + F.elu(torch.sparse.mm(adj, self.mp1(h)))
            h = h + F.elu(torch.sparse.mm(adj, self.mp2(h)))
        else:
            # Same depth and parameter count, message passing removed, so the
            # graph is the only difference against the kg rows.
            h = h + F.elu(self.mp1(h))
            h = h + F.elu(self.mp2(h))
        return self.head(h).squeeze(-1)


def validation_score(scores, val_pos, pool):
    """Median rank of held-out positives among genes the model never trained on.

    Lower is better. val_pos are 2022-09 panel genes withheld from training;
    pool is the held-out unlabelled fold. Both are unseen, so the comparison is
    fair, and no post-cutoff target label is consulted - epoch selection never
    sees the evaluation set.
    """
    candidates = np.concatenate([val_pos, pool])
    order = candidates[np.argsort(-scores[candidates], kind="stable")]
    rank_of = {g: r + 1 for r, g in enumerate(order)}
    return float(np.median([rank_of[g] for g in val_pos]))


def run_fold(X, adj, y, train_mask, val_pos, pool, use_graph, dims, fusion,
             hidden, epochs, lr, pos_weight, dropout, weight_decay, patience,
             eval_every, device, seed):
    """Train one outer fold, selecting the stopping epoch on inner validation.

    Without this the model simply trains to convergence, and because the
    literature embeddings are far easier to memorise than expression, "which
    feature set is better" degenerates into "which overfits more slowly".
    SPEOS gets epoch selection from its inner CV folds; this is the minimal
    equivalent.
    """
    torch.manual_seed(seed)
    model = FusionGNN(dims, hidden, fusion, use_graph, dropout).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    w = torch.tensor([pos_weight], device=device)

    best_score, best_state, best_epoch = np.inf, None, 0
    for epoch in range(1, epochs + 1):
        model.train()
        opt.zero_grad()
        out = model(X, adj)
        loss = F.binary_cross_entropy_with_logits(
            out[train_mask], y[train_mask], pos_weight=w)
        loss.backward()
        opt.step()

        if epoch % eval_every:
            continue
        model.eval()
        with torch.no_grad():
            scores = model(X, adj).cpu().numpy()
        score = validation_score(scores, val_pos, pool)
        if score < best_score:
            best_score, best_epoch = score, epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        elif epoch - best_epoch >= patience:
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        return torch.sigmoid(model(X, adj)).cpu().numpy(), best_epoch


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disease", default="dee", choices=sorted(DISEASES))
    parser.add_argument("--preset", default="all",
                        help="'all', or a comma-separated subset of preset names")
    parser.add_argument("--hidden", type=int, default=50)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--pos-weight", type=float, default=5.0)
    parser.add_argument("--dropout", type=float, default=0.5)
    parser.add_argument("--weight-decay", type=float, default=5e-4)
    parser.add_argument("--val-frac", type=float, default=0.2,
                        help="fraction of positives withheld for epoch selection")
    parser.add_argument("--eval-every", type=int, default=10)
    parser.add_argument("--patience", type=int, default=50,
                        help="stop after this many epochs with no validation gain")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--device", default="auto")
    parser.add_argument("-o", "--out", default=os.path.join(HERE, "simple_gnn_metrics.tsv"))
    parser.add_argument("--ranks-out", default=None,
                        help="also write per-target ranks, which is what the "
                             "paired contrasts need - comparing marginal CIs "
                             "between configurations is the wrong test")
    args = parser.parse_args()

    device = args.device
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    print("device: {}".format(device))

    pos_file, tgt_file = DISEASES[args.disease]
    positives = read_genes(os.path.join(DATA, "diseases", pos_file))
    targets = read_genes(os.path.join(DATA, "diseases", tgt_file))

    blocks = {k: load_block(v) for k, v in FEATURE_FILES.items()}
    genes = sorted(set.intersection(*(set(b) for b in blocks.values())))
    index = {g: i for i, g in enumerate(genes)}
    print("universe: {} genes".format(len(genes)))

    rng = np.random.default_rng(args.seed)
    blocks["random"] = {g: rng.standard_normal(100).astype(np.float32) for g in genes}

    adj, n_edges = build_adjacency(genes, index, device)
    print("graph: {:,} unique undirected edges".format(n_edges))

    is_pos = np.array([g in positives for g in genes])
    y = torch.tensor(is_pos.astype(np.float32), device=device)
    pos_idx = np.flatnonzero(is_pos)
    unl_idx = np.flatnonzero(~is_pos)
    print("positives: {}, unlabelled: {}\n".format(len(pos_idx), len(unl_idx)))

    chosen = PRESETS if args.preset == "all" else [
        p for p in PRESETS if p[0] in args.preset.split(",")]

    results = []
    per_gene = []
    print("{:22}{:>8}{:>10}  {:22}{:>7}{:>8}".format(
        "configuration", "targets", "median", "95% CI", "epoch", "time"))
    print("-" * 85)

    for name, block_names, graph, fusion in chosen:
        mats = [np.vstack([blocks[b][g] for g in genes]) for b in block_names]
        dims = [m.shape[1] for m in mats]
        X = torch.tensor(np.hstack(mats), device=device)
        # Standardise per column; the blocks are on very different scales
        # (expression, embeddings, raw counts) and the additive fusions in
        # particular are sensitive to that.
        X = (X - X.mean(0)) / (X.std(0) + 1e-6)

        started = time.time()
        scores = np.zeros(len(genes))
        # Reseed per configuration so every row sees the identical fold split
        # and validation positives. Sharing one stream across presets would
        # make the partition depend on how many configurations ran before,
        # so an ablation would differ in its CV split as well as in the thing
        # being ablated, and batching the run would change the numbers.
        rng = np.random.default_rng(args.seed)
        folds = np.array_split(rng.permutation(unl_idx), args.folds)
        stopped_at = []
        for f in range(args.folds):
            held = folds[f]
            # Withhold a slice of the positives from this fold for epoch
            # selection, so the stopping point is chosen on genes the model
            # is not being fitted to.
            shuffled = rng.permutation(pos_idx)
            n_val = max(1, int(round(args.val_frac * len(shuffled))))
            val_pos, train_pos = shuffled[:n_val], shuffled[n_val:]

            train = np.concatenate(
                [train_pos] + [folds[j] for j in range(args.folds) if j != f])
            mask = torch.zeros(len(genes), dtype=torch.bool, device=device)
            mask[torch.tensor(train, device=device)] = True
            out, best_epoch = run_fold(
                X, adj, y, mask, val_pos, held, graph == "kg", dims, fusion,
                args.hidden, args.epochs, args.lr, args.pos_weight,
                args.dropout, args.weight_decay, args.patience,
                args.eval_every, device, args.seed + f)
            scores[held] = out[held]
            stopped_at.append(best_epoch)

        order = unl_idx[np.argsort(-scores[unl_idx], kind="stable")]
        rank_of = {genes[i]: r + 1 for r, i in enumerate(order)}
        hit_genes = [g for g in sorted(targets) if g in rank_of]
        hits = [rank_of[g] for g in hit_genes]
        for g in hit_genes:
            # Carry the disease on every row. Configuration names repeat across
            # diseases, so a rank file without this cannot be told apart from
            # another disease's once the files are globbed together.
            per_gene.append({"disease": args.disease, "configuration": name,
                             "gene": g, "rank": rank_of[g],
                             "universe_size": len(order)})
        point, bounds = bootstrap(hits, len(order), args.n_boot, args.seed)

        record = {"disease": args.disease, "configuration": name,
                  "features": "+".join(block_names), "graph": graph,
                  "fusion": fusion if len(block_names) > 1 else "-",
                  "n_targets": len(hits), "universe_size": len(order),
                  "mean_stop_epoch": round(float(np.mean(stopped_at)), 1)}
        for k, v in point.items():
            record[k] = round(v, 4)
            if k in bounds:
                record[k + "_lo"] = round(bounds[k][0], 4)
                record[k + "_hi"] = round(bounds[k][1], 4)
        results.append(record)

        ci = bounds.get("median_rank_unseen")
        print("{:22}{:>8}{:>10}  {:22}{:>7.0f}{:>7.0f}s".format(
            name, len(hits), "{:g}".format(point["median_rank_unseen"]),
            "[{:g}, {:g}]".format(*ci) if ci else "-",
            np.mean(stopped_at), time.time() - started))

    cols = []
    for r in results:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(args.out, "w", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(results)
    print("\nWrote {} rows -> {}".format(len(results), args.out))

    if args.ranks_out:
        with open(args.ranks_out, "w", newline="") as handle:
            w = csv.DictWriter(
                handle, delimiter="\t",
                fieldnames=["disease", "configuration", "gene", "rank",
                            "universe_size"])
            w.writeheader()
            w.writerows(per_gene)
        print("Wrote {} per-gene ranks -> {}".format(len(per_gene), args.ranks_out))


if __name__ == "__main__":
    main()
