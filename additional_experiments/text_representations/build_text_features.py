"""
Classical text representations as a control for the sentence transformer.
(Reviewer 1, comments 4 and 5a)

R1.4: "The sentence transformer is essentially being used as a generic
text-to-vector representation of PubMed information associated with each gene.
Classical text representations such as TF-IDF, TF-IDF+SVD/LSA, or Doc2Vec would
provide important controls. Without these, the results end up showing that
adding literature-derived features helps, rather than that contextual
transformer representations provide meaningful additional value."

The point is fair: nothing so far separates "literature helps" from "MiniLM
helps". This builds TF-IDF and TF-IDF+SVD representations from the SAME
date-filtered text the MiniLM embeddings were built from, at the same
dimensionality, so the only thing that differs is the encoder.

That last part matters. Two files exist on Spartan:

    /data/projects/punim2353/chathura/pubmed/gene_details_2022_09.csv
    /data/projects/punim2353/chathura/pubmed/gene_paper_details_2022_09.csv

and it is not certain which holds titles+abstracts and which holds titles only.
kiml/generate_pubmed_embeddings.py reads gene_details_2022_09.csv, so that is
presumably the one behind the published embeddings - but building TF-IDF from
titles only and comparing it against MiniLM built from abstracts would make the
comparison unfair in our favour, which is precisely the kind of thing R1.4 is
probing. So this script INSPECTS both first and reports what it finds, and
refuses to proceed silently on the wrong one.

Run with --inspect-only first, read the report, then run for real.

Outputs a matrix in the same format the SPEOS pipeline expects - one row per
gene, whitespace-separated, gene symbol first - so it can be dropped into
extensions/datasets*.json exactly like the MiniLM file.

Usage on Spartan, from the KIML root:

    # 1. work out which file is which
    python additional_experiments/text_representations/build_text_features.py \
        --inspect-only

    # 2. build the representations from whichever holds the fuller text
    python additional_experiments/text_representations/build_text_features.py \
        --input /data/projects/punim2353/chathura/pubmed/gene_details_2022_09.csv \
        --method tfidf_svd --dim 384
"""

import argparse
import csv
import os
import statistics
import sys

DEFAULT_CANDIDATES = [
    "/data/projects/punim2353/chathura/pubmed/gene_details_2022_09.csv",
    "/data/projects/punim2353/chathura/pubmed/gene_paper_details_2022_09.csv",
]

# MiniLM's output width. Matching it means a difference in downstream results
# is attributable to the representation, not to feature count.
MINILM_DIM = 384


def split_title(text):
    """From 'Title: X Abstract: Y' return X; from unlabelled text return it whole.

    Only gene_paper_details_2022_09.csv carries the labels, which is what makes
    a title-only arm possible at all - gene_details_2022_09.csv has them
    stripped and the two fields cannot be separated again.
    """
    lowered = text.lower()
    start = lowered.find("title:")
    if start < 0:
        return None  # unlabelled: cannot isolate the title
    start += len("title:")
    end = lowered.find("abstract:", start)
    return text[start:end if end >= 0 else None].strip()


def read_gene_documents(path, limit=None, scope="full"):
    """-> (gene, [per-paper text, ...]) pairs. One row per gene, ragged.

    scope="title" keeps only the title of each paper, which requires the
    labelled file; papers without a recoverable title are dropped.
    """
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # header
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                return
            if not row:
                continue
            cells = [cell for cell in row[1:] if cell.strip()]
            if scope == "title":
                cells = [t for t in (split_title(c) for c in cells) if t]
            yield row[0].strip(), cells


def inspect(path, sample=400):
    """Report enough to tell titles-only from titles+abstracts."""
    if not os.path.exists(path):
        return {"path": path, "exists": False}

    lengths, papers, examples = [], [], []
    for gene, docs in read_gene_documents(path, limit=sample):
        papers.append(len(docs))
        for doc in docs:
            lengths.append(len(doc.split()))
        if docs and len(examples) < 2:
            examples.append((gene, docs[0]))

    if not lengths:
        return {"path": path, "exists": True, "parsed": False}

    return {
        "path": path,
        "exists": True,
        "parsed": True,
        "size_mb": os.path.getsize(path) / 1e6,
        "genes_sampled": len(papers),
        "median_papers_per_gene": statistics.median(papers),
        "median_words_per_paper": statistics.median(lengths),
        "mean_words_per_paper": sum(lengths) / len(lengths),
        "max_words_per_paper": max(lengths),
        "examples": examples,
    }


def report(findings):
    print("=" * 78)
    print(" INSPECTION - which file holds the fuller text?")
    print("=" * 78)
    for f in findings:
        print("\n{}".format(f["path"]))
        if not f.get("exists"):
            print("   NOT FOUND")
            continue
        if not f.get("parsed"):
            print("   could not parse any rows")
            continue
        print("   size {:.0f} MB, {} genes sampled".format(f["size_mb"], f["genes_sampled"]))
        print("   papers per gene : median {:g}".format(f["median_papers_per_gene"]))
        print("   words per paper : median {:g}, mean {:.0f}, max {}".format(
            f["median_words_per_paper"], f["mean_words_per_paper"],
            f["max_words_per_paper"]))
        for gene, text in f["examples"]:
            print("   e.g. {}: {}{}".format(gene, text[:110].replace("\n", " "),
                                            "..." if len(text) > 110 else ""))

    usable = [f for f in findings if f.get("parsed")]
    if len(usable) < 2:
        print("\nOnly one file readable; use that one.")
        return
    print("\n" + "-" * 78)
    fuller = max(usable, key=lambda f: f["median_words_per_paper"])
    thinner = min(usable, key=lambda f: f["median_words_per_paper"])
    ratio = (fuller["median_words_per_paper"]
             / max(thinner["median_words_per_paper"], 1))
    print(" VERDICT")
    print("   fuller text : {}".format(os.path.basename(fuller["path"])))
    print("                 median {:g} words per paper".format(
        fuller["median_words_per_paper"]))
    print("   thinner     : {}".format(os.path.basename(thinner["path"])))
    print("                 median {:g} words per paper".format(
        thinner["median_words_per_paper"]))
    # Two files can hold the same text and differ only by field labels. A
    # near-identical word count plus "Title:"/"Abstract:" prefixes in one of
    # them means exactly that, and reporting a 1.01x ratio as "similar, check
    # manually" is useless.
    def labelled(f):
        return any(t.lstrip().lower().startswith("title:") or "abstract:" in t.lower()
                   for _, t in f["examples"])

    if ratio < 1.2 and labelled(fuller) != labelled(thinner):
        with_labels = fuller if labelled(fuller) else thinner
        without = thinner if labelled(fuller) else fuller
        print("\n   SAME TEXT, different formatting. {} carries literal".format(
            os.path.basename(with_labels["path"])))
        print("   'Title:' / 'Abstract:' prefixes; {} has them".format(
            os.path.basename(without["path"])))
        print("   stripped. The word-count gap is just those tokens.")
        print("\n   Use {} - it is the file".format(os.path.basename(without["path"])))
        print("   generate_pubmed_embeddings.py reads, so the MiniLM embeddings were")
        print("   built from exactly this text and the comparison isolates the encoder.")
        print("   (The labels would in any case be neutralised by TF-IDF: a term in")
        print("   every document has zero inverse document frequency.)")
    elif ratio > 3:
        print("\n   A {:.0f}x difference is consistent with titles+abstracts versus".format(ratio))
        print("   titles only. Build from the FULLER file: the MiniLM embeddings")
        print("   were built from abstracts, and comparing a titles-only TF-IDF")
        print("   against them would understate the classical baseline, which is")
        print("   exactly the bias R1.4 is testing for.")
    else:
        print("\n   The two are similar in length, so both probably hold the same")
        print("   kind of text. Check the examples above before choosing.")
    print("=" * 78)


def build(path, method, dim, min_df, max_features, out_path, seed, scope="full"):
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    print("Reading {}".format(path))
    if scope == "title":
        # Probe WITH the scope applied, over enough genes that a few legitimately
        # title-less papers do not look like a wrong-file error.
        probe = list(read_gene_documents(path, limit=50, scope=scope))
        if not any(docs for _, docs in probe):
            print("[error] --text-scope title needs the labelled file, the one whose")
            print("        entries look like 'Title: ... Abstract: ...'. No titles were")
            print("        recoverable from the first {} genes of this file.".format(
                len(probe)))
            print("        Use gene_paper_details_2022_09.csv.")
            return 1
    print("  text scope: {}".format(
        "title only" if scope == "title" else "title + abstract"))

    genes, documents = [], []
    for gene, docs in read_gene_documents(path, scope=scope):
        genes.append(gene)
        # One document per gene: all of its papers concatenated, matching how
        # the MiniLM embeddings average over a gene's papers.
        documents.append(" ".join(docs))
    print("  {} genes".format(len(genes)))

    empty = sum(1 for d in documents if not d.strip())
    if empty:
        print("  [warn] {} genes have no text; they will get all-zero vectors "
              "and should be expected to rank poorly".format(empty))

    print("Fitting TF-IDF (min_df={}, max_features={})".format(min_df, max_features))
    vectorizer = TfidfVectorizer(min_df=min_df, max_features=max_features,
                                 stop_words="english", sublinear_tf=True)
    matrix = vectorizer.fit_transform(documents)
    print("  vocabulary {}, matrix {}".format(len(vectorizer.vocabulary_), matrix.shape))

    if method == "tfidf_svd":
        # TruncatedSVD requires n_components < n_features and fails with an
        # opaque error otherwise. A vocabulary smaller than the requested width
        # means min_df is too aggressive, or the text is thinner than expected -
        # which is exactly the titles-only case this script warns about.
        if matrix.shape[1] <= dim:
            print("[error] vocabulary is {} terms but {} dimensions were requested."
                  .format(matrix.shape[1], dim))
            print("        Lower --min-df (currently {}), raise --max-features, or "
                  "check that".format(min_df))
            print("        --input points at the file with the fuller text.")
            return 1
        print("Reducing to {} dimensions with truncated SVD".format(dim))
        svd = TruncatedSVD(n_components=dim, random_state=seed)
        features = svd.fit_transform(matrix)
        print("  explained variance {:.1%}".format(svd.explained_variance_ratio_.sum()))
    elif method == "tfidf":
        if matrix.shape[1] > dim:
            print("[error] raw TF-IDF has {} columns; SPEOS expects a dense matrix "
                  "of manageable width. Use --method tfidf_svd, or lower "
                  "--max-features to {}.".format(matrix.shape[1], dim))
            return 1
        features = matrix.toarray()
    else:
        print("[error] unknown method {}".format(method))
        return 1

    print("Writing {}".format(out_path))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w") as handle:
        for gene, vector in zip(genes, features):
            handle.write(gene + " " + " ".join("{:.6f}".format(v) for v in vector) + "\n")
    print("  {} rows x {} dims".format(len(genes), features.shape[1]))
    print("\nNext: register this file in external/SPEOS/extensions/ as a datasets")
    print("entry using preprocess_mydata_expression, then generate configs that")
    print("point at it instead of the MiniLM embeddings.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=None,
                        help="gene->text CSV. If omitted, both candidates are inspected.")
    parser.add_argument("--candidates", nargs="*", default=DEFAULT_CANDIDATES)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--method", default="tfidf_svd", choices=["tfidf", "tfidf_svd"])
    parser.add_argument("--text-scope", default="full", choices=["full", "title"],
                        help="'full' uses title+abstract; 'title' keeps only the "
                             "title of each paper and requires the labelled file. "
                             "Running both separates what abstracts contribute "
                             "from what titles alone already carry.")
    parser.add_argument("--dim", type=int, default=MINILM_DIM,
                        help="output width; defaults to MiniLM's {} so the "
                             "comparison isolates the encoder".format(MINILM_DIM))
    parser.add_argument("--min-df", type=int, default=5)
    parser.add_argument("--max-features", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    if args.inspect_only or not args.input:
        report([inspect(p) for p in args.candidates])
        if args.inspect_only:
            return 0
        print("\nRe-run with --input pointing at the file you chose.")
        return 0

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "pubmed_{}_{}_{}d_2022_09.txt".format(args.method, args.text_scope, args.dim))
    return build(args.input, args.method, args.dim, args.min_df,
                 args.max_features, out, args.seed, args.text_scope)


if __name__ == "__main__":
    sys.exit(main())
