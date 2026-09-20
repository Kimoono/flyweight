"""Drop-in check of the Janelia MaleCNS v1.0 connectome (brain + ventral nerve cord, CC-BY):
downloads the flat tables (~1.2 GB, no login), builds data/cache_malecns.npz in the same format
as cache_783.npz and data/neurons_malecns.json with the same group names, then runs the
findings stimuli through the unchanged Brain class.

    python sim/build_malecns.py            # download + build + test (~10 min, ~4 GB RAM)

Results (20 Sep 2026) are in docs/findings.md, "MaleCNS drop-in check". Not used by the game."""
import json, subprocess, sys, time
from pathlib import Path
import numpy as np, pandas as pd, scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "data" / "upstream" / "malecns"; UP.mkdir(parents=True, exist_ok=True)
BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
FILES = {"body-annotations.feather": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
         "body-neurotransmitters.feather": "body-neurotransmitters-male-cns-v1.0.feather",
         "connectome-weights.feather": "connectome-weights-male-cns-v1.0-minconf-0.5.feather"}
for local, remote in FILES.items():
    if not (UP / local).exists():
        print("downloading", remote, flush=True)
        subprocess.run(["curl", "-L", "-C", "-", "--progress-bar", "-o", str(UP / local), f"{BASE}/{remote}"], check=True)

W_SYN, MIN_W = 0.275, 5     # as sim/brain.py and the FlyWire 5-synapse threshold
t0 = time.time()
a = pd.read_feather(UP / "body-annotations.feather"); a = a[a.status == "Traced"]
ids = a.bodyId.values.astype(np.int64); n = len(ids); index = pd.Series(np.arange(n), index=ids)
nt = pd.read_feather(UP / "body-neurotransmitters.feather").set_index("body")["consensus_nt"].str.lower()
sign = nt.map({"acetylcholine": 1.0, "gaba": -1.0, "glutamate": -1.0}).reindex(ids).fillna(0.0).values  # amines dropped
w = pd.read_feather(UP / "connectome-weights.feather"); w = w[w.weight >= MIN_W]
pre = index.reindex(w.body_pre.values).values; post = index.reindex(w.body_post.values).values
ok = ~np.isnan(pre) & ~np.isnan(post); pre, post = pre[ok].astype(np.int64), post[ok].astype(np.int64)
val = w.weight.values[ok].astype(np.float32) * sign[pre].astype(np.float32) * W_SYN; keep = val != 0
W = sp.csc_matrix((val[keep], (post[keep], pre[keep])), shape=(n, n))
np.savez(ROOT / "data" / "cache_malecns.npz", ids=ids, data=W.data, indices=W.indices, indptr=W.indptr, shape=np.array(W.shape))
print(f"{n} traced neurons, {W.nnz:,} signed connections, built in {time.time() - t0:.0f}s", flush=True)

t, sc = a.type.fillna(""), a.subclass.fillna("")
side = a.somaSide.map({"L": "left", "R": "right"}).fillna(a.rootSide.map({"L": "left", "R": "right"}))
def grp(mask): return {s: [str(x) for x in a.bodyId[mask & (side == s)]] for s in ("left", "right")}
senses = {"eye_target": grp(t == "LC10a"), "shadow": grp(t.isin(["LPLC2", "LC4"])), "motion": grp(t == "LC9"),
          "taste_proxy": grp(sc.isin(["taste peg", "labellar bristle", "taste bristle"])),   # sugar/bitter NOT annotated in MaleCNS
          "pharynx": grp(sc == "pharyngeal sensillum")}
outputs = {"turn": grp(t == "DNa02"), "turn_aux": grp(t == "DNa01"), "walk": grp(t == "DNp09"), "escape": grp(t == "DNp01"),
           "escape_aux": grp(t.isin(["DNp02", "DNp04", "DNp11"])), "feed": grp(t == "MN9"), "jump_muscle": grp(t == "TTMn"),
           "leg_motor": grp(a.superclass.fillna("").eq("vnc_motor") & ~t.isin(["TTMn"]) & ~t.str.contains("DLMn|DVMn|CvN|GNG", regex=True))}
(ROOT / "data" / "neurons_malecns.json").write_text(json.dumps(
    {"source": "Janelia FlyEM MaleCNS v1.0 (CC-BY); body IDs as strings", "senses": {k: {**v, "label": k, "status": ""} for k, v in senses.items()},
     "outputs": {k: {**v, "label": k} for k, v in outputs.items()}}))

sys.path.insert(0, str(ROOT / "sim")); import brain as B
B.CACHE = ROOT / "data" / "cache_malecns.npz"
br = B.Brain(dt=0.5, neurons_json=ROOT / "data" / "neurons_malecns.json")
for label, inp in [("eye_target left", {"eye_target": {"left": 150}}), ("eye_target right", {"eye_target": {"right": 150}}),
                   ("shadow left", {"shadow": {"left": 150}}), ("motion left", {"motion": {"left": 150}}),
                   ("taste_proxy both 40", {"taste_proxy": {"left": 40, "right": 40}}), ("pharynx both 40", {"pharynx": {"left": 40, "right": 40}})]:
    br.reset(); br.set_input(inp); t1 = time.time(); out, active = br.step(400)
    print(f"{label:20s} active={active:5d} {(time.time() - t1) / 0.4:.1f} s wall per sim s | "
          + "  ".join(f"{k}:{v['left']:.0f}/{v['right']:.0f}" for k, v in out.items() if max(v.values()) > 0), flush=True)
