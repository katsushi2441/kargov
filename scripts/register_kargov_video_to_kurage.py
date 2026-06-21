#!/usr/bin/env python3
"""Register a kargov-produced MP4 as a Kurage public video job.

This is intentionally deterministic: it copies the MP4 into Kurage's
storage/jobs/{job_id}/output.mp4, creates a thumbnail, writes the job JSON,
and prints the public kuragev.php URL.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path, help="kargov final MP4 path")
    parser.add_argument("--kurage-root", type=Path, default=Path("/home/kojima/work/kurage"))
    parser.add_argument("--title", default="Kurage AI VTuber / kdeck / kargov demo")
    parser.add_argument("--summary", default="kargovで録画したKurage AI VTuberとkdeck連携のデモ動画です。")
    parser.add_argument("--article-url", default="")
    parser.add_argument("--source", default="kargov")
    parser.add_argument("--content-type", default="kvtuber_kdeck_demo")
    parser.add_argument("--job-id", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    video = args.video.expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")

    jobs_dir = args.kurage_root.expanduser().resolve() / "storage" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = args.job_id.strip() or uuid.uuid4().hex[:16]
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    output = job_dir / "output.mp4"
    thumbnail = job_dir / "thumbnail.jpg"
    shutil.copy2(video, output)
    subprocess.run(
        [
            "/usr/bin/ffmpeg",
            "-y",
            "-ss",
            "4",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(thumbnail),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    job = {
        "status": "done",
        "progress": 100,
        "source": args.source,
        "content_type": args.content_type,
        "title": args.title,
        "display_title": args.title,
        "summary_title": args.title,
        "tweet_author": "Kurage Argo Video",
        "tweet_author_name": "Kurage AI VTuber / kdeck / kargov",
        "tweet_url": args.article_url,
        "article_url": args.article_url,
        "tweet_text": args.summary,
        "summary": args.summary,
        "display_summary": args.summary,
        "video_file": str(output),
        "thumbnail_file": str(thumbnail),
        "created_at": now,
        "updated_at": now,
        "views": 0,
        "script": {
            "title": args.title,
            "scenes": [
                {"index": 0, "narration": args.summary, "duration": 10},
            ],
        },
        "kargov_video_file": str(video),
    }
    (jobs_dir / f"{job_id}.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "job_id": job_id,
        "url": f"https://kurage.exbridge.jp/kuragev.php?id={job_id}",
        "video_file": str(output),
        "thumbnail_file": str(thumbnail),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
