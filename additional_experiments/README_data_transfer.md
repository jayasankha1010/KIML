# Moving data between Spartan and the laptop

Git is the wrong tool for the large artefacts these experiments produce. The
feature matrices are ~60–70 MB each as float text, and there are now eight of
them; prediction files are small individually but there are dozens. Pushing
them through GitHub makes every clone and every pull slow, on both machines.

Use git for **code and small results** — scripts, configs, metric TSVs of a few
KB. Use `rsync` for **data**.

## What belongs where

| artefact | size | git? |
|---|---|---|
| scripts, SLURM files, configs | KB | yes |
| metric tables (`*_metrics.tsv`, `*_contrasts.tsv`) | KB | yes |
| `pubmed_counts_2022_09.tsv` | ~1 MB | yes — small and awkward to regenerate |
| feature matrices (`pubmed_*_384d_*.txt`) | 60–70 MB each | **no** — rsync |
| per-gene predictions (`*_probabilities.tsv`) | ~600 KB × dozens | **no** — rsync |
| SPEOS fold outputs (`results/`) | hundreds of MB | **no** — already gitignored |

The matrices and predictions are now in `.gitignore`. They are regenerable:
matrices from the PubMed corpus via `text_representations/`, predictions by
re-running the SLURM jobs.

## Pulling results down from Spartan

Set this once:

```bash
SPARTAN=yourusername@spartan.hpc.unimelb.edu.au
KIML=/data/gpfs/projects/punim0512/chathura_projects/KIML
```

Prediction files from a batch of runs:

```bash
rsync -avz --progress \
  "$SPARTAN:$KIML/external/SPEOS/results_processing/*_probabilities.tsv" \
  additional_experiments/revision_runs/paper_predictions/
```

Feature matrices:

```bash
rsync -avz --progress \
  "$SPARTAN:$KIML/additional_experiments/text_representations/*.txt" \
  additional_experiments/text_representations/
```

Metric tables are small, so git handles those fine — no rsync needed.

## Pushing data up to Spartan

Rarely needed, since code goes via git and data is generated there. If you do:

```bash
rsync -avz --progress additional_experiments/text_representations/ \
  "$SPARTAN:$KIML/additional_experiments/text_representations/"
```

## Tips

- `-z` compresses in transit. Float text compresses well — a 66 MB matrix moves
  as roughly 20 MB.
- `--dry-run` first if you are unsure what a pattern will match.
- rsync skips files that already match, so re-running after a partial transfer
  is cheap.
- If the connection is unreliable, add `--partial` so interrupted transfers
  resume rather than restart.

## About the history

The matrices were committed in `d792604` before these rules existed, so roughly
320 MB sits in git history and will be re-downloaded on every fresh clone.
Removing it requires rewriting history (`git filter-repo` or BFG) followed by a
force-push and a re-clone on Spartan.

That is a one-time coordinated operation, not an emergency. Adding the ignore
rules stops the problem growing; decide separately whether the existing history
is worth rewriting. If the repository is going to be cited in the paper as the
public artefact, it probably is — a reader cloning it should not have to pull
320 MB of regenerable intermediate data.
