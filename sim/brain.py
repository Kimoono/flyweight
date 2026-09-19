"""Whole-brain leaky integrate-and-fire simulator for the FlyWire v783 connectome.

Pure numpy/scipy re-implementation of Shiu et al.'s Brian2 model
(https://github.com/philshiu/Drosophila_brain_model), with a *stepping* API so a
game loop can change sensory input while the brain keeps running.

    brain = Brain()                       # loads + caches the connectome
    brain.set_input({"eye_target": {"left": 150}})   # Hz per group/side
    out = brain.step(50)                  # advance 50 ms -> firing rates of outputs
"""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "data" / "upstream" / "Drosophila_brain_model"
CACHE = ROOT / "data" / "cache_783.npz"

# Model constants (Shiu et al. 2024, model.py default_params), in mV / ms
V_REST, V_RESET, V_TH = -52.0, -52.0, -45.0
T_MBR, TAU, T_RFC, T_DLY = 20.0, 5.0, 2.2, 1.8
W_SYN, F_POI = 0.275, 250


def load_connectome():
    """Returns (ids, W) with W[post, pre] in mV, CSC so columns = a neuron's outputs."""
    if CACHE.exists():
        z = np.load(CACHE)
        W = sp.csc_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"]))
        return z["ids"], W
    import pandas as pd
    comp = pd.read_csv(UP / "Completeness_783.csv", index_col=0)
    con = pd.read_parquet(UP / "Connectivity_783.parquet")
    n = len(comp)
    W = sp.csc_matrix(
        (con["Excitatory x Connectivity"].values.astype(np.float32) * W_SYN,
         (con["Postsynaptic_Index"].values, con["Presynaptic_Index"].values)), shape=(n, n))
    ids = comp.index.values.astype(np.int64)
    np.savez(CACHE, ids=ids, data=W.data, indices=W.indices, indptr=W.indptr, shape=W.shape)
    return ids, W


class Brain:
    def __init__(self, dt: float = 0.1, seed: int = 0, neurons_json: Path | None = None):
        self.dt = dt
        self.ids, self.W = load_connectome()
        self.n = len(self.ids)
        self.index = {int(f): i for i, f in enumerate(self.ids)}
        self.rng = np.random.default_rng(seed)
        self.groups = {}
        nj = neurons_json or ROOT / "data" / "neurons.json"
        if nj.exists():
            raw = json.loads(nj.read_text())
            for kind in ("senses", "outputs"):
                for name, g in raw[kind].items():
                    for side in ("left", "right"):
                        self.groups[(name, side)] = np.array(
                            [self.index[int(x)] for x in g[side] if int(x) in self.index], dtype=np.int64)
            self.output_names = list(raw["outputs"])
        self.reset()

    def reset(self):
        n = self.n
        self.v = np.full(n, V_REST, np.float32)
        self.g = np.zeros(n, np.float32)
        self.ref = np.zeros(n, np.int32)
        self.dly = max(1, int(round(T_DLY / self.dt)))
        self.rfc = max(1, int(round(T_RFC / self.dt)))
        self.buf = [np.empty(0, np.int64)] * self.dly
        self.t = 0
        self.ex = np.empty(0, np.int64)      # stimulated neuron indices
        self.ex_p = np.empty(0, np.float32)  # per-step spike probability

    def set_input(self, rates: dict, extra: dict | None = None):
        """rates = {"sugar": {"left": 80, "right": 80}, ...} in Hz.
        extra = {neuron_index_array_key: ...} not needed for the game."""
        idx, p = [], []
        for name, sides in rates.items():
            for side, hz in sides.items():
                if hz > 0:
                    gidx = self.groups[(name, side)]
                    idx.append(gidx); p.append(np.full(len(gidx), hz * self.dt / 1000.0, np.float32))
        self.ex = np.concatenate(idx) if idx else np.empty(0, np.int64)
        self.ex_p = np.concatenate(p) if p else np.empty(0, np.float32)

    def set_input_indices(self, indices, hz):
        self.ex = np.asarray(indices, np.int64)
        self.ex_p = np.full(len(self.ex), hz * self.dt / 1000.0, np.float32)

    def step(self, ms: float, return_counts: bool = False):
        """Advance the brain by `ms`. Returns {output: {"left": Hz, "right": Hz}}
        (mean rate over this window), or the raw spike-count vector."""
        W, dt = self.W, self.dt
        a = np.float32(dt / T_MBR); b = np.float32(1.0 - dt / TAU)
        counts = np.zeros(self.n, np.int32)
        v, g, ref = self.v, self.g, self.ref
        for _ in range(int(round(ms / dt))):
            act = ref <= 0
            v += act * (a * (V_REST - v + g))
            g *= np.where(act, b, np.float32(1))
            ref -= 1
            if len(self.ex):
                hit = self.ex[self.rng.random(len(self.ex)) < self.ex_p]
                v[hit] += W_SYN * F_POI
            inc = self.buf[self.t % self.dly]
            if len(inc):
                lo = W.indptr[inc]; ln = W.indptr[inc + 1] - lo
                tot = int(ln.sum())
                if tot:
                    sel = np.repeat(lo - np.r_[0, np.cumsum(ln)[:-1]], ln) + np.arange(tot)
                    rows = W.indices[sel]
                    np.add.at(g, rows, W.data[sel] * act[rows])
            spk = np.flatnonzero(v > V_TH)
            v[spk] = V_RESET; g[spk] = 0; ref[spk] = self.rfc
            ref[self.ex] = 0                      # stimulated neurons: no refractory (as upstream)
            counts[spk] += 1
            self.buf[self.t % self.dly] = spk
            self.t += 1
        if return_counts:
            return counts
        sec = ms / 1000.0
        return {name: {s: float(counts[self.groups[(name, s)]].mean() / sec) if len(self.groups[(name, s)]) else 0.0
                       for s in ("left", "right")} for name in self.output_names}, int((counts > 0).sum())


if __name__ == "__main__":
    import sys
    dt = float(sys.argv[1]) if len(sys.argv) > 1 else 0.1
    t0 = time.time(); br = Brain(dt=dt); print(f"loaded {br.n} neurons in {time.time()-t0:.1f}s, dt={dt} ms")
    tests = [("eye_target left", {"eye_target": {"left": 150}}),
             ("shadow left", {"shadow": {"left": 150}}),
             ("sugar both", {"sugar": {"left": 80, "right": 80}}),
             ("sugar+bitter", {"sugar": {"left": 80, "right": 80}, "bitter": {"left": 150, "right": 150}})]
    for label, inp in tests:
        br.reset(); br.set_input(inp); t0 = time.time(); out, active = br.step(400); w = time.time() - t0
        line = "  ".join(f"{k}:{v['left']:.0f}/{v['right']:.0f}" for k, v in out.items() if max(v.values()) > 0)
        print(f"{label:16s} active={active:5d} {w/0.4:.1f} s wall per simulated s | {line}")
