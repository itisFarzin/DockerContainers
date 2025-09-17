#!/usr/bin/env python3

import os
import shutil
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: install the 'pyyaml' package.")
    exit(1)


class Config:
    config: dict[str, str | int | list]
    default_values = {
        "containers_folder": "containers",
        "composes_folder": "composes",
        "network_name": "cloud",
        "network_driver": "bridge",
        "subnet": "172.20.0.0/24",
        "restart_policy": "unless-stopped",
        "use_full_directory": True,
        "bind_path": "/home/docker/Docker",
        "output": "docker-compose.yaml",
    }

    def __init__(self):
        with open("config/generate.yaml", "r") as file:
            self.config = yaml.safe_load(file)

    def get(self, key: str):
        return (
            os.getenv(key.upper())
            or self.config.get(key.lower())
            or self.default_values.get(key)
        )


def main():
    config = Config()

    containers_folder: str = config.get("containers_folder")
    composes_folder: str = config.get("composes_folder")
    network: str = config.get("network_name")
    network_driver: str = config.get("network_driver")
    subnet: str = config.get("subnet")
    gateway: str = subnet.rsplit(".", 1)[0] + ".1"
    restart_policy: str = config.get("restart_policy")
    use_full_directory: bool = str(
        config.get("use_full_directory")
    ).lower() in {"true", "1"}
    bind_path: str = config.get("bind_path")
    output: str = config.get("output")

    main_template = yaml.safe_load(
        open("templates/main-compose.yaml")
        .read()
        .lstrip()
        .format(
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
        "network",
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
        "depends_on",
        "healthcheck",
        "ports",
    )

    def generate(container: dict[str, str | list]):
        name = container.get("name", path.stem)
        folder = container.get("folder", name)
        used_volumes = []
        result = {
            "image": container["image"],
            "hostname": name,
            "container_name": name,
            "restart": container.get("restart", restart_policy),
        }

        for option in options:
            if value := container.get(option):
                _value = []
                if option == "devices":
                    for device in value:
                        parts = device.rsplit(":")
                        if len(parts) == 1:
                            parts.append(parts[0])

                        _value.append(":".join(parts))
                elif option == "volumes":
                    custom_binds = list(
                        filter(
                            lambda volume: (
                                (split_volume := volume.split(":"))
                                and (
                                    len(split_volume) == 1
                                    or (
                                        len(split_volume) == 2
                                        and split_volume[-1] in {"ro", "rw"}
                                    )
                                )
                            ),
                            value,
                        )
                    )

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
                result[option] = _value or value

        if "network_mode" not in container:
            result["networks"] = [network]

        return result

    for path in sorted(
        list(Path(containers_folder).glob("*.yaml"))
        + list(Path(containers_folder).glob("*.yml"))
    ):
        used_names = []

        service: dict[str, dict] = yaml.safe_load(
            service_template.format(network=network)
        )
        service["services"] = {}

        with open(path, "r") as file:
            containers: list[dict[str, str | list]] = list(
                yaml.safe_load_all(file)
            )

        for container in containers:
            name = container.get("name", path.stem)
            if name in used_names:
                number = str(used_names.count(name) + 1)
                container["name"] = name = f"{name}_{number}"
                if container["folder"]:
                    container["folder"] += number

            used_names.append(name)
            service["services"][name] = generate(container)
            main_template["services"][name] = yaml.safe_load(
                composes_template.format(
                    name=name, path=composes_folder + "/" + path.name
                )
            )

        with open(f"{composes_folder}/{path.stem}.yaml", "w") as compose:
            yaml.dump(service, compose, sort_keys=False)

    with open(output, "w") as file:
        yaml.dump(main_template, file, sort_keys=False)


if __name__ == "__main__":
    main()
