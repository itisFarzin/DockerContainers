#!/usr/bin/env python3
try:
    import yaml
except ImportError:
    print("ERROR: install pyyaml package.")
    exit(1)

from pathlib import Path

containers_folder = "containers"
composes_folder = "composes"

network = "test_network"
subnet = "172.20.0.0/24"
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

with open("docker-compose.yaml", "w") as f:
    f.write(template)
