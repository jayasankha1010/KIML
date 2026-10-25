# Submitting the remaining seed runs — handover guide

You are submitting GPU jobs on Spartan for the KIML paper revision. Everything
is already set up: configs are generated, the pipeline is tested, and DEE is
being handled separately. **You only need to submit jobs and confirm they
worked.** No code changes, no config generation.

Budget roughly **117 jobs at ~1–1.5 h each**, run four at a time, so about a day
and a half of wall time if you work through it disease by disease.

---

## Why we are doing this

Reviewer 1 asked for confidence intervals on the main results table. The
published numbers came from a **single run each**, and the model is not
seeded — SPEOS never calls `torch.manual_seed` — so repeating a run gives a
different answer. We measured one case where the median rank moved by 633
positions between two runs of an identical configuration.

So we are running every main-table configuration **five times** and will report
the spread. Three methods, nine diseases, five seeds.

---

## Setup (once)

```bash
ssh <your-username>@spartan.hpc.unimelb.edu.au
cd /data/gpfs/projects/punim2353/chathura/KIML
```

Check you can read it and that the manifest is there:

```bash
wc -l external/SPEOS/revision_manifest.txt    # expect 144
```

**Which account to use.** Jobs must charge an allocation you belong to:

```bash
sacctmgr show assoc user=$USER format=account
```

Use any account from that list in the `--account=` flag below. The account
charges *compute* only — output files go to punim2353 regardless, which is
where the space is. If you are not a member of punim2353 and cannot write
there, stop and contact Chathura rather than cloning your own copy; a separate
checkout would renumber every job index in this guide.

---

## The one rule that matters

**Do NOT run `make_configs.py`.** The configs already exist, and regenerating
them without `--append` deletes every `Rev_*.yaml` and renumbers the manifest,
which invalidates all the indices you are about to compute. If something looks
wrong, ask rather than regenerate.

---

## Submitting one disease

Work through **one disease at a time**. Pick from:

```
ad_dee   ar_dee   microcephaly   intellectual_disability
mnd      cp       platelet_disorder   arthrogryposis
```

(`dee` is already being handled — skip it.)

### Step 1 — build the index list

Set the disease, then run this block unchanged. It selects the three main-table
methods for that disease and **skips anything that already has results**, so it
is safe to re-run and will not redo finished work.

```bash
DISEASE=ad_dee          # <-- change this each time
ACCOUNT=punim2353       # <-- your account from sacctmgr

grep -nE "^Rev_${DISEASE}_(GNN|CGNN|KIGNN)_s[0-9]+$" \
     external/SPEOS/revision_manifest.txt > /tmp/kiml_candidates.txt

IDX=""
while IFS=: read -r line name; do
    if [ -f "external/SPEOS/results_processing/${name}_probabilities.tsv" ]; then
        echo "  skip (already done): $name"
        continue
    fi
    IDX="${IDX}${IDX:+,}$((line - 1))"
done < /tmp/kiml_candidates.txt

echo "indices: $IDX"
```

### Step 2 — check it picked the right jobs

```bash
echo "$IDX" | tr ',' '\n' | while read -r i; do
    printf "%4s  %s\n" "$i" "$(sed -n "$((i+1))p" external/SPEOS/revision_manifest.txt)"
done
```

You should see up to 15 lines: `GNN_s1..s5`, `CGNN_s1..s5`, `KIGNN_s1..s5` for
your chosen disease, minus any already done. If you see a different disease, or
names with suffixes like `-PPI`, `-TFIDF` or `KIMLP`, **stop** — those belong to
a different experiment.

### Step 3 — submit

```bash
sbatch --account="$ACCOUNT" --array="${IDX}%4" \
    additional_experiments/revision_runs/run_revision.slurm
```

`%4` limits it to four concurrent jobs. **Do not remove it.** Each run writes
about 120 checkpoint files, and an unthrottled array is what exhausted the
filesystem quota last time and killed a batch mid-write.

---

## Step 4 — the one check that matters

As soon as the first job starts running, before you walk away:

```bash
squeue -u $USER
grep -m1 "scratch:" logs/rev_*.stdout | tail -1
```

That line **must** contain `punim2353`. If it says `punim0512`, the jobs are
writing temporary files to a filesystem that is 97% full and they will die
part-way through. Cancel immediately and contact Chathura:

```bash
scancel <jobid>
```

---

## Checking results

A finished job ends with `[Success]` in its `.stdout`:

```bash
grep -l "^\[Success\]" logs/rev_<jobid>_*.stdout | wc -l    # how many succeeded
grep -L "^\[Success\]" logs/rev_<jobid>_*.stdout            # which did not
```

The real output is one file per run:

```bash
ls external/SPEOS/results_processing/Rev_${DISEASE}_*_probabilities.tsv | wc -l
```

Each should be **17,283 lines** (17,282 genes plus a header):

```bash
wc -l external/SPEOS/results_processing/Rev_${DISEASE}_*_probabilities.tsv
```

Once a disease is complete and verified, move to the next one. Repeat from
Step 1.

---

## Freeing space as you go

Each run leaves ~120 checkpoint files behind. Once a run has produced its
`_probabilities.tsv`, those checkpoints are **no longer needed** — that file is
the result.

Check usage periodically:

```bash
check_project_usage
```

If punim2353 climbs past about 80% on either bytes or files, delete
checkpoints for runs that already have results. Ask Chathura before deleting
anything if you are unsure — the `_probabilities.tsv` files must be kept.

---

## If something fails

**Jobs die immediately.** Read the top of the `.stdout`; the script prints a
clear `[Error]` for missing configs, missing conda env, or unwritable scratch.

**Jobs die part-way with `PytorchStreamWriter ... file write failed`.** The
filesystem is full. Run `check_project_usage` and stop submitting.

**A job reports failure but the `_probabilities.tsv` file exists.** The run
actually succeeded and only the final evaluation step failed. The result is
usable — note it and move on. This happened before with a filename-parsing bug,
now fixed, but flag it if you see it again.

**Anything else.** Save the job id and send the last 30 lines of both the
`.stdout` and `.err`:

```bash
tail -30 logs/rev_<jobid>_<index>.stdout
tail -30 logs/rev_<jobid>_<index>.err
```

---

## When a disease is done

Tell Chathura which disease finished and how many runs succeeded. He will pull
the results down with:

```bash
rsync -avz --partial --progress \
  "spartan:/data/gpfs/projects/punim2353/chathura/KIML/external/SPEOS/results_processing/Rev_*_probabilities.tsv" \
  additional_experiments/revision_runs/paper_predictions/
```

You do not need to run that yourself.

---

## Quick reference

| | |
|---|---|
| Working directory | `/data/gpfs/projects/punim2353/chathura/KIML` |
| Manifest | `external/SPEOS/revision_manifest.txt` (144 lines) |
| Results land in | `external/SPEOS/results_processing/*_probabilities.tsv` |
| Logs | `logs/rev_<jobid>_<index>.{stdout,err}` |
| Throttle | always `%4` |
| Never | run `make_configs.py` |
| Always check | the `scratch:` line says punim2353 |
| Diseases left | ad_dee, ar_dee, microcephaly, intellectual_disability, mnd, cp, platelet_disorder, arthrogryposis |
