#!/usr/bin/env python3

import os
import shutil
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: install the 'pyyaml' package.")
    exit(1)


def main():
    containers_folder: str = os.getenv("CONTAINERS_FOLDER") or "containers"
    composes_folder: str = os.getenv("COMPOSES_FOLDER") or "composes"
    network: str = os.getenv("NETWORK_NAME") or "cloud"
    network_driver: str = os.getenv("NETWORK_DRIVER") or "bridge"
    subnet: str = os.getenv("SUBNET") or "172.20.0.0/24"
    gateway: str = subnet.rsplit(".", 1)[0] + ".1"
    restart_policy: str = os.getenv("RESTART_POLICY") or "unless-stopped"
    use_full_directory: bool = (
        (os.getenv("USE_FULL_DIRECTORY") or "true").lower() in {"true", "1"}
    )
    bind_path: str = os.getenv("BIND_PATH") or "/home/docker/Docker"
    output: str = os.getenv("OUTPUT") or "docker-compose.yaml"

    main_template = yaml.safe_load(
        open("templates/main-compose.yaml").read().lstrip().format(
            network=network,
            driver=network_driver,
            subnet=subnet,
            gateway=gateway,
        )
    )
    main_template["services"] = {}
    composes_template = open("templates/composes.yaml").read().lstrip()
    service_template = open("templates/services.yaml").read().lstrip()

    if os.path.exists(composes_folder):
        shutil.rmtree(composes_folder)

    os.mkdir(composes_folder)

    options = (
        "command",
        "network_mode",
        "user",
        "entrypoint",
        "cap_add",
        "cap_drop",
        "sysctls",
        "labels",
        "devices",
        "volumes",
        "environment",
        "depends_on"
        "healthcheck",
        "ports",
    )

    for path in sorted(
        list(Path(containers_folder).glob("*.yaml"))
        + list(Path(containers_folder).glob("*.yml"))
    ):
        container = open(path, "r")
        data: dict[str, str | list] = yaml.safe_load(container)
        name = data.get("name", path.stem)
        folder = data.get("folder", name)
        service: dict[str, dict] = yaml.safe_load(
            service_template.format(
                name=name,
                image=data["image"],
                restart=restart_policy,
                network=network,
            )
        )

        used_volumes = []

        for option in options:
            if value := data.get(option):
                _value = []
                if option == "devices":
                    for device in value:
                        parts = device.rsplit(":")
                        if len(parts) == 1:
                            parts.append(parts[0])

                        _value.append(":".join(parts))
                elif option == "volumes":
                    custom_binds = list(filter(
                        lambda volume: (
                            (split_volume := volume.split(":")) and
                            (len(split_volume) == 1 or (
                                len(split_volume) == 2
                                and split_volume[-1] in {"ro", "rw"}
                            ))
                        ),
                        value
                    ))

                    for volume in value:
                        cname = ""
                        if ";" in volume:
                            volume, cname = volume.split(";")

                        parts = volume.rsplit(":")
                        suffix = (
                            parts[-1] if parts[-1] in {"ro", "rw"} else None
                        )

                        if suffix:
                            parts = parts[:-1]

                        if len(parts) == 1:
                            _path = f"{bind_path}/{folder}"
                            _volume = cname or parts[0].rsplit("/")[-1]

                            if _volume in used_volumes:
                                _volume = (
                                    f"{_volume}"
                                    f"{used_volumes.count(_volume) + 1}"
                                )

                            if not (
                                use_full_directory and len(custom_binds) == 1
                            ):
                                _path += f"/{_volume}"

                            parts = [_path, parts[0]]

                        if suffix:
                            parts.append(suffix)

                        used_volumes.append(parts[0].rsplit("/")[-1])
                        _value.append(":".join(parts))
                service["services"][name][option] = _value or value

        if "network_mode" not in data:
            service["services"][name]["networks"] = [network]

        with open(f"{composes_folder}/{name}.yaml", "w") as compose:
            yaml.dump(service, compose, sort_keys=False)

        main_template["services"][name] = yaml.safe_load(
            composes_template.format(
                name=name, path=composes_folder + "/" + path.name
            )
        )

        container.close()

    with open(output, "w") as file:
        yaml.dump(main_template, file, sort_keys=False)


if __name__ == "__main__":
    main()
