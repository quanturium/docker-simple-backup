import argparse
import os
import time
from pathlib import Path
import importlib
import string
from datetime import datetime
from crontab import CronTab
import docker
from docker_simple_backup.service.service_interface import ServiceInterface
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Main configuration
DSB_SOURCE_DIR = "/etc/docker-simple-backup/data"
DSB_DESTINATION_DIR = "/etc/docker-simple-backup/archive"
DSB_DOCKER_SOCKET = "/var/run/docker.sock"
DSB_SERVICE = "local"  # local, gdrive
DSB_ARCHIVE_NAME = "backup-%Y-%m-%dT%H-%M-%S"
DSB_ROTATION_COUNT = 10
# Service: local
DSB_LOCAL_DIR = "/backups"
# Service: gdrive
DSB_GDRIVE_CREDENTIALS_FILE = "/etc/docker-simple-backup/gdrive_credentials.json"
DSB_GDRIVE_FOLDER_ID = None
# Labels
DSB_STOP_DURING_BACKUP_LABEL = "docker-simple-backup.stop-during-backup"
DSB_EXEC_CUSTOM_BACKUP_LABEL = "docker-simple-backup.exec-custom-backup"


def create_archive(
    docker_service, pattern: str, source: Path, destination: Path
) -> Path:
    if not source.exists():
        raise Exception("Source folder does not exists: " + source.as_posix())
    # Stop labeled containers for data safefy
    containers = docker_service.containers.list(
        filters={"label": DSB_STOP_DURING_BACKUP_LABEL + "=true"}
    )
    try:
        stop_docker_containers(docker_service, containers)
        log.info("Creating archive...")
        archive_name = datetime.today().strftime(pattern) + ".zip"
        archive_path = destination / archive_name
        destination.mkdir(parents=True, exist_ok=True)
        os.system("zip -qr " + archive_path.as_posix() + " " + source.as_posix())
        log.info("Archive created: " + archive_name)
        return archive_path
    except Exception:
        log.exception("Archive error")
        raise
    finally:
        # Make sure we restart the containers
        start_docker_containers(docker_service, containers)


def cleanup(dir: Path) -> None:
    for x in dir.iterdir():
        x.unlink()


def to_camel_case(s: str):
    return string.capwords(s, sep="_").replace("_", "")[0:] if s else s


def create_service(args):
    service_name = args.service
    service_module = "docker_simple_backup.service." + service_name + "_service"
    service_class = to_camel_case(service_name + "_service")
    MyClass = getattr(importlib.import_module(service_module), service_class)
    return MyClass(args)


def stop_docker_containers(docker: docker.DockerClient, containers):
    if len(containers) > 0:
        log.info("Stopping labeled containers...")
        for x in containers:
            x.stop()
            log.info("Container stopped: " + x.name)


def start_docker_containers(docker: docker.DockerClient, containers):
    if len(containers) > 0:
        log.info("Starting back labeled containers...")
        for x in containers:
            x.start()
            log.info("Container started: " + x.name)


def run_custom_backup(docker: docker.DockerClient):
    log.info("Looking for custom backups...")
    # Include all since it might have been stopped
    containers = docker.containers.list(filters={"label": DSB_EXEC_CUSTOM_BACKUP_LABEL})
    log.info("Custom backups found: " + str(len(containers)))
    if len(containers) > 0:
        log.info("Executing custom backups...")
        for x in containers:
            cmd = x.labels[DSB_EXEC_CUSTOM_BACKUP_LABEL]
            log.info("Executing for container: " + x.name)
            result = x.exec_run(cmd)
            for n in result.output.decode("utf-8").splitlines():
                log.info(x.name + ">" + str(n))


def process_archive_with_service(
    service: ServiceInterface, archive: Path, old_archive_count: int
):
    log.info("Processing archive with service...")
    try:
        service.copy_archive(archive)
        service.remove_old_archives(old_archive_count)
        log.info("Service completed")
    except Exception:
        log.exception("Service failed")


def run_with_service(service, args):
    log.info("Starting backup...")
    docker_service = docker.DockerClient(base_url="unix://" + args.docker_socket)
    try:
        run_custom_backup(docker_service)  # First, run custom backups
        archive = create_archive(
            docker_service,
            args.name,
            Path(args.source_dir),
            Path(args.destination_dir),
        )  # Archive custom backup and mounted volumes
        if archive is None:
            raise Exception("Archive empty due to archiving failure")
        process_archive_with_service(service, archive, args.rotation_max_count)
        log.info("Backup completed: success")
        cleanup(Path(args.destination_dir))
    except Exception:
        log.exception("Backup completed: error")


def run(args):
    try:
        service = create_service(args)
        run_with_service(service, args)
    except Exception as ex:
        log.error(ex)


def schedule_run(args):
    try:
        entry = CronTab(args.schedule)
        offset = entry.next(default_utc=True)
        next_run = time.time() + offset
        while True:
            if time.time() >= next_run:
                run(args)
                offset = entry.next(default_utc=True)
                next_run = time.time() + offset
            else:
                log.info(
                    "Next backup scheduled for: "
                    + str(datetime.fromtimestamp(next_run))
                )
                time.sleep(offset + 1)
    except ValueError:
        log.exception("Invalid --schedule value")


def main():
    parser = argparse.ArgumentParser(description="Simple backup tool")
    parser.add_argument(
        "--schedule",
        nargs="?",
        help="A cron-like schedule to continuously run it. By default run as a one-off script",
    )
    parser.add_argument(
        "--source-dir",
        nargs="?",
        default=DSB_SOURCE_DIR,
        help="Source directory of the data you want to backup (Default: %(default)s)",
    )
    parser.add_argument(
        "--destination-dir",
        nargs="?",
        default=DSB_DESTINATION_DIR,
        help="Destination directory of the archived data (Default: %(default)s)",
    )
    parser.add_argument(
        "--docker-socket",
        nargs="?",
        default=DSB_DOCKER_SOCKET,
        help="Path to the docker socket (Default: %(default)s)",
    )
    parser.add_argument(
        "--rotation-max-count",
        nargs="?",
        default=DSB_ROTATION_COUNT,
        help="Number of backup copies to keep (Default: %(default)s)",
    )
    parser.add_argument(
        "--name",
        nargs="?",
        default=DSB_ARCHIVE_NAME,
        help="Name of your backup file through `date` command (Default: %(default)s)",
    )
    parser.add_argument(
        "--service",
        nargs="?",
        default=DSB_SERVICE,
        choices=["local", "gdrive"],
        help="Service to be used for persisting the backup. (Default: %(default)s)",
    )
    parser.add_argument(
        "--service-local-dir",
        nargs="?",
        help="Required if `service` is `local`. Specify the path of the backups",
    )
    parser.add_argument(
        "--service-gdrive-credentials",
        nargs="?",
        default=DSB_GDRIVE_CREDENTIALS_FILE,
        help="Required if `service` is `gdrive`. Specify the path to the service account credentials (Default: %(default)s)",
    )
    parser.add_argument(
        "--service-gdrive-folder",
        nargs="?",
        help="Required if `service` is `gdrive`. Specify the folder id to store the backups into",
    )
    args = parser.parse_args()
    if args.schedule is None:
        run(args)
    else:
        schedule_run(args)


if __name__ == "__main__":
    main()
