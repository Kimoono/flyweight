"""Builds data/blocks.json: the Neuron Jenga blocks. Each block is a nameable part of the
brain (plain-language label + one-line description) with the simulator indices of its
neurons (Completeness_783 order, like data/positions.bin), from the official annotations
(Schlegel et al. 2024).
Random blocks carry a fraction instead of IDs; the server draws them fresh on every pull."""
import json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data/upstream/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
COMP = ROOT / "data/upstream/Drosophila_brain_model/Completeness_783.csv"

ids = pd.read_csv(COMP, index_col=0).index.values
a = pd.read_csv(ANN, sep="\t", low_memory=False).set_index("root_id")
a = a[~a.index.duplicated()].reindex(ids)
sc, cc, ct, sub, side = a.super_class.fillna(""), a.cell_class.fillna(""), a.cell_type.fillna(""), a.cell_sub_class.fillna(""), a.side.fillna("")

BLOCKS = [  # (id, label, description, mask)   - order = how they appear on the host page
    ("giant_fibre", "The giant fibre", "2 neurons. The famous escape wire, straight from the eyes to the legs.", ct == "DNp01"),
    ("steering", "The steering pair", "2 neurons that turn the fly (one per side).", ct == "DNa02"),
    ("descending", "All brain-to-body cables", "1,299 descending neurons: every command that leaves the brain.", sc == "descending"),
    ("mouth_motor", "Mouth & neck motor neurons", "105 motor neurons that live in the brain, including the tongue.", cc == "brain_motor_neuron"),
    ("taste", "Taste sensors", "408 taste neurons: sugar, bitter, water, on the tongue and legs.", cc == "gustatory"),
    ("object_detectors", "Object detectors", "8,038 visual projection neurons: 'something is there', 'something is coming'.", sc == "visual_projection"),
    ("optic_lobes", "The optic lobes (half the brain!)", "77,530 neurons that process raw pixels behind each eye.", sc == "optic"),
    ("memory", "Memory centre", "5,177 Kenyon cells: the mushroom body, where a fly learns.", cc == "Kenyon_Cell"),
    ("dopamine", "Dopamine: reward & punishment", "331 dopamine neurons that teach the memory centre.", cc == "DAN"),
    ("smell", "Smell centre", "3,417 neurons of the antennal lobe: the nose of the brain.", cc.isin(["olfactory", "ALPN", "ALLN", "ALIN", "ALON"])),
    ("navigation", "Navigation centre", "2,875 central complex neurons: the fly's compass.", cc == "CX"),
    ("touch_hearing", "Touch & hearing", "2,656 mechanosensory neurons: antennae, bristles, ears.", cc == "mechanosensory"),
    ("left_half", "The whole LEFT half", "69,000 neurons: everything on the left side.", side == "left"),
    ("right_half", "The whole RIGHT half", "69,000 neurons: everything on the right side.", side == "right"),
]
RANDOM = [
    ("random5", "A random 5%", "6,900 neurons picked at random. Different every pull.", 0.05),
    ("random20", "A random 20%", "27,700 neurons picked at random. Different every pull.", 0.20),
]
out = []
for bid, label, desc, mask in BLOCKS:
    out.append({"id": bid, "label": label, "desc": desc, "indices": np.flatnonzero(mask.values).tolist()})
    print(f"{bid:18s} {int(mask.sum()):6d}  {label}")
for bid, label, desc, frac in RANDOM:
    out.append({"id": bid, "label": label, "desc": desc, "random": frac})
(ROOT / "data/blocks.json").write_text(json.dumps({"source": "FlyWire v783 annotations", "blocks": out}))
print("->", ROOT / "data/blocks.json", f"{(ROOT / 'data/blocks.json').stat().st_size / 1e6:.1f} MB")
