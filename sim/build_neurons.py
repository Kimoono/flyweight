"""Builds data/neurons.json: FlyWire root IDs for every game sense and motor output,
split by brain side, from the official FlyWire annotations (Schlegel et al. 2024)."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANN = ROOT / "data/upstream/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
COMP = ROOT / "data/upstream/Drosophila_brain_model/Completeness_783.csv"

a = pd.read_csv(ANN, sep="\t", low_memory=False)
a = a[a.root_id.isin(pd.read_csv(COMP, index_col=0).index)]
ct = a.cell_type.fillna("")

SENSES = {  # name: (mask, plain-language label, status)
    "eye_target": (ct == "LC10a", "Object seen by this eye (pursuit neurons LC10a)", "works"),
    "shadow":     (ct.isin(["LPLC2", "LC4"]), "Looming shadow on this side (LPLC2 + LC4)", "works"),
    "motion":     (ct == "LC9", "Movement seen by this eye (LC9)", "works"),
    "sugar":      (a.cell_sub_class == "sugar/water", "Sugar/water taste neurons", "works - keep <= 80 Hz"),
    "bitter":     (a.cell_sub_class == "bitter", "Bitter taste neurons", "works"),
    "sound":      (a.cell_sub_class == "auditory", "Johnston's organ auditory neurons", "experimental - asymmetric"),
    "antenna_touch": (a.cell_sub_class == "grooming", "Antennal touch (JO grooming neurons)", "experimental - no readout yet"),
    "smell_vinegar": (ct == "ORN_DM1", "Vinegar smell (ORN DM1)", "BROKEN - triggers olfactory runaway"),
}
OUTPUTS = {
    "turn":     (ct == "DNa02", "Steering: fly turns toward the side that fires more (DNa02)"),
    "turn_aux": (ct == "DNa01", "Steering, second channel (DNa01)"),
    "walk":     (ct == "DNp09", "Forward walking / pursuit drive (DNp09)"),
    "escape":   (ct == "DNp01", "Giant fiber: escape jump (DNp01)"),
    "escape_aux": (ct.isin(["DNp02", "DNp04", "DNp11"]), "Other looming-escape descending neurons"),
    "backward": (ct == "MDN", "Moonwalker: walk backwards (MDN)"),
    "feed":     (ct == "CB0701", "Proboscis extension motor neuron MN9 (annotated CB0701)"),
}

def pack(mask):
    return {s: [str(x) for x in a[mask & (a.side == s)].root_id] for s in ("left", "right")}

out = {"source": "FlyWire v783 annotations; IDs as strings (exceed JS safe integer range)",
       "senses": {k: {**pack(m), "label": l, "status": st} for k, (m, l, st) in SENSES.items()},
       "outputs": {k: {**pack(m), "label": l} for k, (m, l) in OUTPUTS.items()}}
(ROOT / "data/neurons.json").write_text(json.dumps(out, indent=1))
for kind in ("senses", "outputs"):
    for k, g in out[kind].items():
        print(f"{kind[:-1]:7s}{k:15s} L={len(g['left']):4d} R={len(g['right']):4d}")
