"""
scripts/setup_dataset.py
=============================================================================
Helper script to clone the official AmbiK dataset from the authors' repository:
https://github.com/cog-model/AmbiK-dataset.git
=============================================================================
Citation:
Anastasia Ivanova, Eva Bakaeva, Zoya Volovikova, Alexey Kovalev, and Aleksandr Panov.
"AmbiK: Dataset of Ambiguous Tasks in Kitchen Environment." ACL 2025.
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "AmbiK-dataset")
REPO_URL = "https://github.com/cog-model/AmbiK-dataset.git"

def setup_dataset():
    if os.path.exists(DATASET_DIR) and (
        os.path.exists(os.path.join(DATASET_DIR, "AmbiK_data.csv")) or 
        os.path.exists(os.path.join(DATASET_DIR, "ambik_dataset"))
    ):
        print(f"[OK] AmbiK dataset is already present at: {DATASET_DIR}")
        return True

    print(f"[*] Downloading AmbiK dataset from official repository ({REPO_URL})...")
    try:
        subprocess.run(["git", "clone", REPO_URL, DATASET_DIR], check=True)
        print(f"[SUCCESS] Dataset successfully cloned into: {DATASET_DIR}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to clone dataset: {e}")
        print(f"Please clone manually: git clone {REPO_URL} {DATASET_DIR}")
        return False

if __name__ == \"__main__\":
    setup_dataset()
