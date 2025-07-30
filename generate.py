#!/usr/bin/env python3
try:
    import yaml
except ImportError:
    print("ERROR: install the pyyaml package.")
    exit(1)

import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Docker compose generator.")
parser.add_argument(
    "--containers",
    type=str,
    help="Containers folder",
    default="containers"
)
parser.add_argument(
    "--composes",
    type=str,
    help="Composes folder",
    default="composes"
)
parser.add_argument(
    "--network",
    type=str,
    help="The network for composes",
    default="test_network"
)
parser.add_argument(
    "--subnet",
    type=str,
    help="The subnet for the composes' network",
    default="172.20.0.0/24"
)
parser.add_argument(
    "-o",
    "--output",
    type=str,
    help="The docker compose output file",
    default="docker-compose.yaml"
)
args = parser.parse_args()

containers_folder = args.containers
composes_folder = args.composes

network = args.network
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

for path in sorted(Path(containers_folder).glob("*.yaml")):
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        name = path.stem
        service = yaml.safe_load(
            service_template.format(name=name, image=data["image"])
        )

        if command := data.get("command"):
            service["services"][name]["command"] = command

        if volumes := data.get("volumes"):
            service["services"][name]["volumes"] = volumes

        if environment := data.get("environment"):
            service["services"][name]["environment"] = environment

        if ports := data.get("ports"):
            service["services"][name]["ports"] = ports

        service["services"][name]["networks"] = [network]

        with open(f"{composes_folder}/{name}.yaml", "w") as file:
            yaml.dump(service, file, sort_keys=False)

        template += apps_template.format(
            name=name, path=composes_folder + "/" + path.name
        )

template += "\n"

with open(args.output, "w") as f:
    f.write(template)
