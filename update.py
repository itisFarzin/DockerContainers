#!/usr/bin/env python3

import os
import re
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


def extract_version(version: str, pattern: str | None) -> str | None:
    if not pattern:
        return version

    match = re.search(pattern, version)
    if match and match.groups():
        return match.group(1)

    return None


def parse_version(version: str | None):
    if not version:
        return None

    try:
        parsed_version = Version(version)
        if not parsed_version.is_prerelease:
            return parsed_version
    except InvalidVersion:
        return None


def main():
    config = Config()
    repo = Repo(".")
    # Discard any changes
    repo.git.reset("--hard")

    containers_folder: str = config.get("containers_folder")
    page_size = int(config.get("page_size"))

    def update(container: dict[str, str | list], page_size: int):
        image = container["image"]
        registry = "docker.io"

        if len(parts := image.split(":")) != 2:
            logging.info(f"Image {image} is invalid.")
            # If an image doesn't specify a version, Docker will append the
            # latest tag by default.
            # This also skip the invalid image formats (e.g. double column)
            return

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
            return

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
            return

        version_regex = data.get("version_regex")

        if not (
            current_version := parse_version(
                extract_version(version, version_regex)
            )
        ):
            logging.warning(
                "Could not parse a comparable version from '{}' for image {}."
                " Skipping.".format(version, full_image)
            )
            return

        versions = None

        if registry == "docker.io":
            user = "library" if user == "_" else user
            result: dict[str, str | dict] = requests.get(
                f"https://hub.docker.com/v2/namespaces/{user}/repositories/"
                f"{image}/tags?page_size={page_size}"
            ).json()

            versions = [
                version["name"] for version in result.get("results", {})
            ]
        elif registry == "ghcr.io":
            token_request: dict = requests.get(
                f"https://ghcr.io/token?scope=repository:{user}/{image}:pull"
            ).json()
            if not (token := token_request.get("token")):
                logging.warning(
                    f'{full_image}: {token_request["errors"][0]["message"]}'
                )
                return

            result: dict[str, str | list] = requests.get(
                f"https://ghcr.io/v2/{user}/{image}/tags/list",
                headers={"Authorization": f"Bearer {token}"},
            ).json()
            versions = result["tags"]

        if not versions:
            return

        versions = [
            (v, version)
            for version in versions
            if (v := parse_version(extract_version(version, version_regex)))
            and v > current_version
        ]

        if not versions:
            return

        newest_version = max(
            versions, key=lambda p: p[0], default=(None, None)
        )[1]
        if not newest_version:
            return

        container["image"] = f"{full_image}:{newest_version}"
        return full_image, image, newest_version

        # TODO: Support other registries.

    for path in sorted(
        list(Path(containers_folder).glob("*.yaml"))
        + list(Path(containers_folder).glob("*.yml"))
    ):
        with open(path, "r") as file:
            containers: list[dict[str, str | list]] = list(
                yaml.safe_load_all(file)
            )

        for container in containers:
            if not (result := update(container, page_size)):
                continue

            full_image, image, newest_version = result
            with open(path, "w") as file:
                yaml.dump_all(containers, file, sort_keys=False)

            repo.index.add([path])
            repo.git.commit(
                "-m",
                f"refactor({path.stem}):"
                f" update {image} to {newest_version}",
            )

            logging.info(f"Updated {full_image} to {newest_version}.")


if __name__ == "__main__":
    main()
