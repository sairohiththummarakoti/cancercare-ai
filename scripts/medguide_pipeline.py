"""Reproducible local dataset ingestion, embedding and vector-search CLI."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medguide import DATA_DIR, MODEL_NAME, find_related_cases, prepare_medguide, read_pipeline_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Download, chunk and embed the complete dataset")
    ingest.add_argument("--revision", help="Pin a specific Hugging Face commit; default resolves current revision")
    ingest.add_argument("--model", default=MODEL_NAME, help="Local FastEmbed model; defaults to fast pretrained static retrieval embeddings")
    ingest.add_argument("--data-dir", type=Path, default=DATA_DIR)
    search = sub.add_parser("search", help="Run a real local vector query")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--disease", help="Exact dataset decision-tree code, e.g. bre_1")
    search.add_argument("--min-similarity", type=float, default=0.3)
    search.add_argument("--data-dir", type=Path, default=DATA_DIR)
    status = sub.add_parser("status")
    status.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    try:
        if args.command == "ingest":
            last = [-1, ""]
            def progress(stage, message, done, total):
                percent = int(100 * done / total) if total else 0
                if stage != last[1] or percent >= last[0] + 5 or done == total:
                    print(f"[{stage}] {message}: {done}/{total}" if total else f"[{stage}] {message}", file=sys.stderr, flush=True)
                    last[:] = [percent, stage]
            value = prepare_medguide(args.data_dir, revision=args.revision, progress=progress, model_name=args.model)
        elif args.command == "search":
            value = find_related_cases(args.query, top_k=args.top_k, disease=args.disease, min_similarity=args.min_similarity, data_dir=args.data_dir)
        else:
            value = read_pipeline_status(args.data_dir)
        print(json.dumps(value, indent=2, ensure_ascii=True))
    except Exception as error:
        if error.__class__.__module__ in {"medguide_ingest", "medguide_vectors"} or type(error) is ValueError:
            print(str(error), file=sys.stderr)
        else:
            print("MedGUIDE processing failed. Check network access, disk space and installed dependencies.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
