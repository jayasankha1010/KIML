"""
Does knowledge inclusion help regardless of model class? (Reviewer 1, comment 3)

R1.3: "The framework is claimed to be general, but experimentally, it is highly
selective towards RF and one GNN implementation ... The same features can be
used with regularized linear models, boosting methods such as XGBoost, MLPs,
encoders, label propagation, KG embeddings, heterogeneous GNNs, etc. I am not
suggesting that the authors test all of these, but merely highlighting that the
choice made by them needs to be defended well enough."

The reviewer is not asking for a benchmark. He is asking whether the reported
benefit is a property of KIML's knowledge features or an artefact of the two
model classes chosen. So the question is narrow:

    does adding literature-derived features help under EVERY model class,
    or only under Random Forest and a FiLM GNN?

This runs the paper's own three feature configurations through four deliberately
plain classifiers. It deliberately does NOT tune anything - the claim under test
is directional (does knowledge help?), not "which model is best", and tuning
would invite exactly the benchmark comparison the reviewer said was unnecessary.

Setup, matching the manuscript's protocol:

  features   LL = child + prebirth cortical expression (159 + 239 dims)
             HL = PubMed MiniLM embeddings, pre-2022-10 (384 dims)
  positives  genes on the DEE panel at 2022-09
  ranking    out-of-fold scores for every non-positive gene
  targets    genes added to the panel after the cutoff
  metrics    identical definitions to results_processing/evaluate_results.py,
             imported from revision_analysis so they cannot drift

Positive-unlabelled handling: unlabelled genes are split into k folds; each fold
is scored by a model trained on all positives plus the OTHER folds' unlabelled
genes as negatives. Every gene is therefore ranked by a model that never saw it
as a negative, which is what makes the ranking honest in a PU setting.

Runs on CPU in a few minutes; no cluster needed.

Usage:
    python additional_experiments/model_classes/run_model_classes.py
"""

import argparse
import csv
import os
import sys

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
from revision_analysis import bootstrap, metrics_from_ranks  # noqa: E402

DATA = os.path.join(ROOT, "data", "kiml_data")
EXPRESSION = [os.path.join(DATA, "ahbd", "child_expression.txt"),
              os.path.join(DATA, "ahbd", "prebirth_expression.txt")]
PUBMED = [os.path.join(DATA, "pubmed_embeddings",
                       "pubmed_embeddings_rearranged_2022_09.txt")]

# disease -> (2022-09 positives, post-split targets). Same files the GNN arm uses.
DISEASES = {
    "dee": ("DEE-2022_09.txt", "DEE-2025_03_vs_2022_09.txt"),
    "cp": ("CP-2022-09.txt", "CP-2025_06_vs_2022_09.txt"),
    "intellectual_disability": ("Intellectual-disability-2022-09.txt",
                                "Intellectual-disability-2025_06_vs_2022_09.txt"),
    "microcephaly": ("Microcephaly-2022-09.txt", "Microcephaly-2025_06_vs_2022_09.txt"),
    "arthrogryposis": ("Arthrogryposis-2022-09.txt", "Arthrogryposis-2025_06_vs_2022_09.txt"),
    "platelet_disorder": ("Bleeding_and_Platelet_Disorders-2022-09.txt",
                          "Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt"),
    "mnd": ("MND-2022-09.txt", "MND-2025_06_vs_2022_09.txt"),
}

FEATURE_SETS = {
    "LL (expression)": EXPRESSION,
    "HL (PubMed)": PUBMED,
    "LL+HL (KIML)": EXPRESSION + PUBMED,
}


def boosting_model(seed):
    """XGBoost if installed, else sklearn's equivalent histogram booster.

    R1.3 names XGBoost specifically, so use it when available and say so in the
    output; HistGradientBoostingClassifier is the same algorithm family and
    keeps the experiment runnable without an extra dependency.
    """
    try:
        from xgboost import XGBClassifier
        return "XGBoost", XGBClassifier(
            n_estimators=300, eval_metric="logloss", random_state=seed, n_jobs=-1)
    except ImportError:
        return ("Gradient boosting",
                HistGradientBoostingClassifier(random_state=seed))


def models(seed):
    """Plain, untuned classifiers. Defaults except for class balancing."""
    boosting_name, boosting = boosting_model(seed)
    return {
        "Logistic regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=2000, class_weight="balanced",
                               random_state=seed)),
        "Random forest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", n_jobs=-1,
            random_state=seed),
        boosting_name: boosting,
        "MLP": make_pipeline(
            StandardScaler(),
            MLPClassifier(hidden_layer_sizes=(50, 50), max_iter=400,
                          random_state=seed)),
    }


def load_matrix(paths):
    """Read whitespace-separated 'gene v1 v2 ...' files and concatenate them."""
    tables = []
    for path in paths:
        values = {}
        with open(path) as handle:
            for line in handle:
                parts = line.split()
                if len(parts) > 1:
                    values[parts[0]] = np.asarray(parts[1:], dtype=np.float64)
        tables.append(values)

    genes = sorted(set.intersection(*(set(t) for t in tables)))
    matrix = np.hstack([np.vstack([t[g] for g in genes]) for t in tables])
    return genes, matrix


def read_genes(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def out_of_fold_scores(X, is_positive, model_factory, n_folds, seed):
    """Score every unlabelled gene with a model that never used it as a negative."""
    scores = np.zeros(len(is_positive))
    positive_idx = np.flatnonzero(is_positive)
    unlabelled_idx = np.flatnonzero(~is_positive)

    folds = KFold(n_splits=n_folds, shuffle=True, random_state=seed)
    for train_part, test_part in folds.split(unlabelled_idx):
        negatives = unlabelled_idx[train_part]
        held_out = unlabelled_idx[test_part]

        train_idx = np.concatenate([positive_idx, negatives])
        y = np.concatenate([np.ones(len(positive_idx)), np.zeros(len(negatives))])

        model = model_factory()
        model.fit(X[train_idx], y)
        scores[held_out] = model.predict_proba(X[held_out])[:, 1]

    return scores, unlabelled_idx


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diseases", nargs="*", default=["dee"],
                        help="subset of {}".format(sorted(DISEASES)))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "model_class_metrics.tsv"))
    args = parser.parse_args()

    results = []
    print("{:24}{:22}{:18}{:>8}{:>10}  {}".format(
        "disease", "model", "features", "targets", "median", "95% CI"))
    print("-" * 98)

    # Features are disease-independent, so load each matrix once.
    loaded = {name: load_matrix(paths) for name, paths in FEATURE_SETS.items()}

    for disease in args.diseases:
        pos_file, tgt_file = DISEASES[disease]
        positives = read_genes(os.path.join(DATA, "diseases", pos_file))
        targets = read_genes(os.path.join(DATA, "diseases", tgt_file))

        for feature_name, (genes, X) in loaded.items():
            is_positive = np.array([g in positives for g in genes])

            for model_name, model in models(args.seed).items():
                factory = (lambda m=model: __import__("sklearn").base.clone(m))
                scores, unlabelled_idx = out_of_fold_scores(
                    X, is_positive, factory, args.folds, args.seed)

                # Rank unlabelled genes by score, highest first - same convention
                # as evaluate_results.py.
                order = unlabelled_idx[np.argsort(-scores[unlabelled_idx], kind="stable")]
                rank_of = {genes[idx]: i + 1 for i, idx in enumerate(order)}
                hit_ranks = [rank_of[g] for g in sorted(targets) if g in rank_of]

                point, bounds = bootstrap(hit_ranks, len(order), args.n_boot, args.seed)
                record = {"disease": disease, "model": model_name,
                          "features": feature_name, "n_targets": len(hit_ranks),
                          "universe_size": len(order), "n_folds": args.folds,
                          "n_boot": args.n_boot}
                for key, value in point.items():
                    record[key] = round(value, 4)
                    if key in bounds:
                        record[key + "_lo"] = round(bounds[key][0], 4)
                        record[key + "_hi"] = round(bounds[key][1], 4)
                results.append(record)

                ci = bounds.get("median_rank_unseen")
                print("{:24}{:22}{:18}{:>8}{:>10}  {}".format(
                    disease, model_name, feature_name, len(hit_ranks),
                    "{:g}".format(point["median_rank_unseen"]),
                    "[{:g}, {:g}]".format(*ci) if ci else "-"))

    columns = list(results[0])
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
