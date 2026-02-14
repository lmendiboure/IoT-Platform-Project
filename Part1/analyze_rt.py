import pandas as pd
import argparse

def summarize(csv_path: str):
    df = pd.read_csv(csv_path)
    jitter = df["jitter_ns"]
    return {
        "file": csv_path,
        "samples": len(df),
        "jitter_mean_ms": jitter.mean() / 1e6,
        "jitter_p95_ms": jitter.quantile(0.95) / 1e6,
        "jitter_p99_ms": jitter.quantile(0.99) / 1e6,
        "jitter_max_ms": jitter.max() / 1e6,
        "miss_rate_%": 100.0 * df["miss"].mean(),
        "dt_mean_ms": df["dt_ns"].mean() / 1e6,
        "dt_max_ms": df["dt_ns"].max() / 1e6,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv_files", nargs="+")
    args = p.parse_args()

    out = pd.DataFrame([summarize(f) for f in args.csv_files])
    print(out.to_string(index=False))

if __name__ == "__main__":
    main()
