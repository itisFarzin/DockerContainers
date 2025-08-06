#!/usr/bin/env python3

import os
try:
    import yaml
except ImportError:
    print("ERROR: install the pyyaml package.")
    exit(1)

import shutil
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Docker compose generator.")
parser.add_argument(
    "--containers-folder",
    type=str,
    help="The containers folder",
    default=os.getenv("CONTAINERS_FOLDER") or "containers"
)
parser.add_argument(
    "--composes-folder",
    type=str,
    help="The composes folder",
    default=os.getenv("COMPOSES_FOLDER") or "composes"
)
parser.add_argument(
    "--network-name",
    type=str,
    help="The network name for the composes",
    default=os.getenv("NETWORK_NAME") or "test_network"
)
parser.add_argument(
    "--subnet",
    type=str,
    help="The subnet for the composes' network",
    default=os.getenv("SUBNET") or "172.20.0.0/24"
)
parser.add_argument(
    "--use-full-directory",
    help="Use full directory binding if no other volumes exist",
    default=(
        (os.getenv("USE_FULL_DIRECTORY") or "true").lower() in {"true", "1"}
    ) or True,
    action=argparse.BooleanOptionalAction
)
parser.add_argument(
    "--bind-path",
    type=str,
    help="The base path for binding the containers' bind volumes",
    default=os.getenv("BIND_PATH") or "/home/docker/Docker"
)
parser.add_argument(
    "-o",
    "--output",
    type=str,
    help="The docker compose output file",
    default=os.getenv("OUTPUT") or "docker-compose.yaml"
)
args = parser.parse_args()

containers_folder = args.containers_folder
composes_folder = args.composes_folder

network = args.network_name
subnet = args.subnet
gateway = subnet.rsplit(".", 1)[0] + ".1"

template = f"""
networks:
  {network}:
    driver: bridge
    name: {network}
    ipam:
      config:
        - subnet: {subnet}
          gateway: {gateway}

services:
""".strip()

apps_template = """
  {name}:
    extends:
      file: {path}
      service: {name}
""".rstrip()

service_template = """
services:
  {name}:
    image: {image}
    hostname: {name}
    container_name: {name}
    restart: unless-stopped
""".lstrip()

if os.path.exists(composes_folder):
    shutil.rmtree(composes_folder)

os.mkdir(composes_folder)

for path in sorted(Path(containers_folder).glob("*.yaml")):
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        name = data.get("name", path.stem)
        folder = data.get("folder", name)
        service = yaml.safe_load(
            service_template.format(name=name, image=data["image"])
        )

        if command := data.get("command"):
            service["services"][name]["command"] = command

        if entrypoint := data.get("entrypoint"):
            service["services"][name]["entrypoint"] = entrypoint

        if volumes := data.get("volumes"):
            _volumes = []
            used_volumes = []
            custom_binds = list(filter(
                lambda volume: (
                    (split_volume := volume.split(":")) and
                    (len(split_volume) == 1 or (
                        len(split_volume) == 2
                        and split_volume[-1] in {"ro", "rw"}
                    ))
                ),
                volumes
            ))

            for volume in volumes:
                cname = ""
                if ";" in volume:
                    volume, cname = volume.split(";")

                parts = volume.rsplit(":")
                suffix = parts[-1] if parts[-1] in {"ro", "rw"} else None

                if suffix:
                    parts = parts[:-1]

                if len(parts) == 1:
                    _path = f"{args.bind_path}/{folder}"
                    _volume = cname or parts[0].rsplit("/")[-1]

                    if _volume in used_volumes:
                        _volume = f"{_volume}{used_volumes.count(_volume)+1}"

                    if not (
                        args.use_full_directory and len(custom_binds) == 1
                    ):
                        _path += f"/{_volume}"

                    parts = [_path, parts[0]]

                if suffix:
                    parts.append(suffix)

                used_volumes.append(parts[0].rsplit("/")[-1])
                _volumes.append(":".join(parts))

            service["services"][name]["volumes"] = _volumes

        if environment := data.get("environment"):
            service["services"][name]["environment"] = environment

        if healthcheck := data.get("healthcheck"):
            service["services"][name]["healthcheck"] = healthcheck

        if ports := data.get("ports"):
            service["services"][name]["ports"] = ports

        service["services"][name]["networks"] = [network]

        with open(f"{composes_folder}/{name}.yaml", "w") as file:
            yaml.dump(service, file, sort_keys=False)

        template += apps_template.format(
            name=name, path=composes_folder + "/" + path.name
        )

with open(args.output, "w") as f:
    f.write(template + "\n")
