"""Usage:  python run_dataset.py <data_dir> <out_dir>      (teachers' dataset: reads/recharges/passes)"""
import sys

from src.dataset_runner import run_dataset

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python run_dataset.py <data_dir> <out_dir>")
    run_dataset(sys.argv[1], sys.argv[2])
