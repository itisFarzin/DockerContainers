#!/usr/bin/env python3

import os
import sys
import logging
import importlib.util
from pathlib import Path

packages = {
    "git": "GitPython",
    "yaml": "PyYAML",
    "requests": "requests",
    "packaging": "packaging",
}
for package, package_name in packages.items():
    if importlib.util.find_spec(package) is None:
        print(f"ERROR: install the '{package_name}' package.")
        exit(1)

import yaml  # noqa: E402
import requests  # noqa: E402
from git import Repo  # noqa: E402
from packaging.version import Version, InvalidVersion  # noqa: E402


logging.basicConfig(
    stream=sys.stdout, format="%(levelname)s: %(message)s", level=logging.INFO
)


class Config:
    _config: dict[str, str | int | list]
    default_values = {
        "containers_folder": "containers",
        "page_size": 40,
    }

    def __init__(self):
        with open("config/update.yaml", "r") as file:
            self._config = yaml.safe_load(file)

    def get(self, key: str):
        return (
            os.getenv(key.upper())
            or self._config.get(key.lower())
            or self.default_values.get(key)
        )


def parse_version(version: str):
    try:
        parsed_version = Version(version)
        if not parsed_version.is_prerelease:
            return parsed_version
    except InvalidVersion:
        pass


def main():
    config = Config()
    repo = Repo(".")
    # Discard any changes
    repo.git.reset("--hard")

    containers_folder: str = config.get("containers_folder")
    page_size = int(config.get("page_size"))

    for path in sorted(
        list(Path(containers_folder).glob("*.yaml"))
        + list(Path(containers_folder).glob("*.yml"))
    ):
        with open(path, "r") as file:
            container: dict[str, str | list] = yaml.safe_load(file)

        image = container["image"]
        version = "latest"
        registry = "docker.io"

        if len(parts := image.split(":")) != 2:
            logging.info(f"Image {image} is invalid.")
            # If an image doesn't specify a version, Docker will append the
            # latest tag by default.
            # This also skip the invalid image formats (e.g. double column)
            continue

        image, version = parts

        if len(parts2 := image.split("/")) == 3:
            registry, user, image = parts2
        elif len(parts2) == 2:
            _var, image = parts2
            if "." in _var:
                registry = _var
                user = "_"
            else:
                user = _var
        elif len(parts2) == 1:
            image = parts2[0]
            user = "_"
        else:
            logging.info(f"Image {image} is invalid.")
            # Skip the invalid image formats
            continue

        full_image = "/".join(
            [registry, image] if user == "_" else [registry, user, image]
        )

        data = next(
            (
                config.get(item)
                for item in [
                    full_image,
                    f"{user}/{image}",
                    image,
                ]
                if item in config._config
            ),
            {},
        )

        if data.get("update") is False:
            logging.info(f"Update for image {full_image} is disabled.")
            continue

        try:
            version = Version(version)
        except InvalidVersion as e:
            logging.debug(e)
            # TODO: Support different types of versions.
            # Skip them for now.
            continue

        if registry == "docker.io":
            _user = "library" if user == "_" else user
            result: dict[str, str | dict] = requests.get(
                f"https://hub.docker.com/v2/namespaces/{_user}/repositories/"
                f"{image}/tags?platforms=true&page_size={page_size}"
            ).json()
            versions = [
                version["name"] for version in result.get("results", {})
            ]
            if newest_version := max(
                (
                    v
                    for v in versions
                    if (_v := parse_version(v)) and _v > version
                ),
                default=None,
            ):
                container["image"] = f"{full_image}:{newest_version}"

                with open(path, "w") as file:
                    yaml.dump(container, file, sort_keys=False)

                repo.index.add([path])
                repo.git.commit(
                    "-m",
                    f"refactor({path.stem}):"
                    f" update {image} to {newest_version}",
                )

                logging.info(f"Updated {full_image} to {newest_version}.")

        # TODO: Support other registries.


if __name__ == "__main__":
    main()
