"""
Does the XGDAG environment actually work? Run this before anything else.

Building the environment and importing torch are not the same as being able
to run XGDAG. PyTorch Geometric's companion libraries (torch-scatter,
torch-sparse) are compiled against a specific torch build, and a mismatch
imports cleanly but fails at the first scatter operation - part-way into a
run, with an error that does not name the real cause.

This exercises the pieces XGDAG actually uses, on a graph the same order of
size as the BioGRID one, so a mismatch surfaces here in seconds.

Usage:
    conda activate xgdag
    python additional_experiments/other_prioritizers/xgdag/envs/verify_env.py
"""

import sys


def check(label, fn):
    try:
        detail = fn()
    except Exception as exc:
        print("  FAIL  {:28} {}: {}".format(label, type(exc).__name__, exc))
        return False
    print("  ok    {:28} {}".format(label, detail if detail else ""))
    return True


def main():
    print("Python {}".format(sys.version.split()[0]))
    ok = True

    def _torch():
        import torch
        return "torch {}  cuda available: {}".format(
            torch.__version__, torch.cuda.is_available())
    ok &= check("torch", _torch)

    def _pyg():
        import torch_geometric
        return "torch_geometric {}".format(torch_geometric.__version__)
    ok &= check("torch_geometric", _pyg)

    # The usual breakage: these import fine but fail when actually called.
    def _scatter():
        import torch
        from torch_scatter import scatter_add
        src = torch.ones(10)
        idx = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3, 4, 4])
        out = scatter_add(src, idx, dim=0)
        assert out.tolist() == [2.0] * 5, out
        return "scatter_add works"
    ok &= check("torch_scatter (runtime)", _scatter)

    def _sparse():
        import torch
        from torch_sparse import SparseTensor
        row = torch.tensor([0, 1, 2])
        col = torch.tensor([1, 2, 0])
        st = SparseTensor(row=row, col=col, sparse_sizes=(3, 3))
        return "SparseTensor {}".format(tuple(st.sizes()))
    ok &= check("torch_sparse (runtime)", _sparse)

    # GraphSAGE on a graph the size of BioGRID - what XGDAG actually trains.
    def _sage():
        import torch
        from torch_geometric.nn import SAGEConv
        n, f = 19761, 6          # BioGRID nodes, six NeDBIT features
        x = torch.randn(n, f)
        edge_index = torch.randint(0, n, (2, 200000))
        conv = SAGEConv(f, 32)
        out = conv(x, edge_index)
        assert out.shape == (n, 32), out.shape
        return "SAGEConv on {}x{} -> {}".format(n, f, tuple(out.shape))
    ok &= check("SAGEConv at BioGRID scale", _sage)

    def _rest():
        import networkx, pandas, sklearn, numpy
        return "networkx {}, pandas {}, sklearn {}, numpy {}".format(
            networkx.__version__, pandas.__version__,
            sklearn.__version__, numpy.__version__)
    ok &= check("networkx/pandas/sklearn", _rest)

    def _extras():
        # Neither is in any of the four shipped CondaEnvs files, but the code
        # imports both. rdkit comes in via SubgraphX, which GDARanking imports
        # unconditionally - so without it even gnnexplainer cannot run.
        import rdkit
        import tensorboardX
        return "rdkit {}, tensorboardX {}".format(
            rdkit.__version__, tensorboardX.__version__)
    ok &= check("rdkit / tensorboardX", _extras)

    def _explainer():
        # XGDAG's ranking stage is built on PyG's explainability module; which
        # names exist moved around between PyG versions, so check rather than
        # assume.
        import torch_geometric.nn as pygnn
        names = [n for n in dir(pygnn) if "Explain" in n]
        if not names:
            raise ImportError("no Explainer class found in torch_geometric.nn")
        return ", ".join(names)
    ok &= check("PyG explainer available", _explainer)

    print()
    if ok:
        print("Environment looks usable. Next: reproduce one of XGDAG's own")
        print("diseases (e.g. C0011581) and check against its shipped Rankings/.")
        return 0
    print("Environment is NOT usable. See envs/xgdag_gpu.yml for fallbacks -")
    print("relaxing the CUDA pin, or installing scatter/sparse from the pyg")
    print("wheel index with pip instead of conda.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
