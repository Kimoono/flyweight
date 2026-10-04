"""Builds data/positions.bin for the brain view: float32 (x, y, z) per model neuron, in the
same index order as the simulator (Completeness_783.csv), NaN where the annotation has no
position. Positions come from the FlyWire annotations (Schlegel et al. 2024) in FlyWire VOXEL
coordinates, not nm: a voxel is 4 x 4 x 40 nm, so z is 10x coarser than x and y (the file spans
203,712 x 97,882 x 6,952 voxels = 815 x 391 x 278 um). The 3D brain view scales z by 10."""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data/upstream/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
COMP = ROOT / "data/upstream/Drosophila_brain_model/Completeness_783.csv"

ids = pd.read_csv(COMP, index_col=0).index.values.astype(np.int64)
a = pd.read_csv(ANN, sep="\t", low_memory=False).set_index("root_id")
a = a[~a.index.duplicated()]
pos = a.reindex(ids)[["pos_x", "pos_y", "pos_z"]].to_numpy(np.float32)
(ROOT / "data/positions.bin").write_bytes(pos.tobytes())
ok = ~np.isnan(pos).any(1)
print(f"{len(ids)} neurons, {ok.sum()} with a position; x {np.nanmin(pos[:,0]):.0f}-{np.nanmax(pos[:,0]):.0f}, "
      f"y {np.nanmin(pos[:,1]):.0f}-{np.nanmax(pos[:,1]):.0f}, z {np.nanmin(pos[:,2]):.0f}-{np.nanmax(pos[:,2]):.0f} nm -> data/positions.bin "
      f"({(ROOT / 'data/positions.bin').stat().st_size/1e6:.1f} MB)")
print("super_class counts:", a.reindex(ids).super_class.value_counts().to_dict())
