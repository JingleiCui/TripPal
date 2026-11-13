"""Consistent local backup, restore rehearsal into a separate DB; never overwrite live DB."""

from pathlib import Path
import sys
import subprocess
import json
import hashlib
import tarfile
import time
import argparse
from datetime import datetime

MODE = "backup"  # backup / verify
BACKUP_DIRECTORY = Path(__file__).resolve().parents[1] / "data/backups"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from travel_agent.config import settings
from travel_agent.db import Session, Task, Document
from sqlalchemy import select


def docker_mysql(sql):
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "mysql", "mysql", "-uroot", "-ptravel_root_local_only"],
        input=sql,
        cwd=ROOT,
        capture_output=True,
        check=True,
    )


def backup():
    folder = BACKUP_DIRECTORY / datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True)
    maintenance = Path(settings.data_dir) / "maintenance"
    maintenance.touch()
    try:
        for _ in range(120):
            with Session() as db:
                running = db.scalar(select(Task.id).where(Task.status == "running").limit(1))
                indexing = db.scalar(select(Document.id).where(Document.status == "indexing").limit(1))
            if not running and not indexing:
                break
            time.sleep(5)
        else:
            raise RuntimeError("尚有执行中任务，未生成不一致备份；请稍后重试")
        with (folder / "database.sql").open("wb") as out:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "mysql",
                    "mysqldump",
                    "-uroot",
                    "-ptravel_root_local_only",
                    "--single-transaction",
                    "--no-tablespaces",
                    "--hex-blob",
                    "travel_agent",
                ],
                cwd=ROOT,
                stdout=out,
                check=True,
            )
        uploads = Path(settings.data_dir) / "uploads"
        uploads.mkdir(exist_ok=True)
        manifest = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in uploads.iterdir() if p.is_file()
        }
        with tarfile.open(folder / "uploads.tar.gz", "w:gz") as tar:
            tar.add(uploads, arcname="uploads")
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (folder / "checksums.json").write_text(
            json.dumps(
                {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()},
                indent=2,
            )
        )
        print(folder)
    finally:
        maintenance.unlink(missing_ok=True)


def verify():
    folder = sorted(p for p in BACKUP_DIRECTORY.iterdir() if p.is_dir())[-1]
    checks = json.loads((folder / "checksums.json").read_text())
    for name, sha in checks.items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == sha, name
    docker_mysql(b"CREATE DATABASE IF NOT EXISTS travel_agent_restore CHARACTER SET utf8mb4;")
    sql = b"USE travel_agent_restore;\n" + (folder / "database.sql").read_bytes()
    docker_mysql(sql)
    result = docker_mysql(
        b"USE travel_agent_restore; SELECT COUNT(*) AS restored_trips FROM trips; SELECT COUNT(*) AS restored_docs FROM documents;"
    )
    manifest = json.loads((folder / "manifest.json").read_text())
    with tarfile.open(folder / "uploads.tar.gz") as tar:
        for name, sha in manifest.items():
            raw = tar.extractfile("uploads/" + name).read()
            assert hashlib.sha256(raw).hexdigest() == sha, name
    print(result.stdout.decode())
    print("文件哈希全部匹配；只恢复到 travel_agent_restore，未覆盖业务库。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["backup", "verify"], default=MODE)
    mode = parser.parse_args().mode
    backup() if mode == "backup" else verify()
