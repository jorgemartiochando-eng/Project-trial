"""Write synthetic CSVs to data/ so you can see the expected file format.

    python scripts/generate_sample_data.py --n 900 --seed 7
"""
import argparse
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import synthetic  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--n", type=int, default=900)
p.add_argument("--seed", type=int, default=7)
args = p.parse_args()

out = Path(__file__).resolve().parent.parent / "data"
out.mkdir(exist_ok=True)
synthetic.generate(n=args.n, seed=args.seed).to_csv(out / "sample_employees.csv", index=False)
synthetic.job_evaluation().to_csv(out / "sample_job_evaluation.csv", index=False)
print(f"Wrote {out / 'sample_employees.csv'} and {out / 'sample_job_evaluation.csv'}")
