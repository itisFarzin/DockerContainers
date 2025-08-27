#!/usr/bin/env python3

import os
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


def parse_version(version: str):
    try:
        parsed_version = Version(version)
        if not parsed_version.is_prerelease:
            return parsed_version
    except InvalidVersion:
        pass


def main():
    repo = Repo(".")
    # Discard any changes
    repo.git.reset("--hard")

    with open("config/update.yaml", "r") as file:
        config: dict[str, str | int | list] = yaml.safe_load(file)

    containers_folder: str = (
        os.getenv("CONTAINERS_FOLDER")
        or config.get("containers_folder")
        or "containers"
    )
    page_size = int(
        os.getenv("PAGE_SIZE")
        or config.get("page_size")
        or 30
    )

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
            # If an image doesn't specify a version, Docker will append the
            # latest tag by default.
            # This also skip the invalid image formats (e.g. double column)
            continue
        image, version = parts

        if len(parts2 := image.split("/")) == 3:
            registry, user, image = parts2
        elif len(parts2) == 2:
            user, image = parts2
        else:
            # Skip the invalid image formats
            continue

        data = next(
            (
                config.get(item)
                for item in [
                    f"{registry}/{user}/{image}", f"{user}/{image}", image
                ]
                if item in config
            ),
            {}
        )

        if data.get("update") is False:
            continue

        try:
            version = Version(version)
        except InvalidVersion:
            # TODO: Support different types of versions.
            # Skip them for now.
            continue

        if registry == "docker.io":
            result: dict[str, str | dict] = requests.get(
                f"https://hub.docker.com/v2/namespaces/{user}/repositories/"
                f"{image}/tags?platforms=true&page_size={page_size}"
            ).json()
            versions = (
                [version["name"] for version in result.get("results", {})]
            )
            if newest_version := max(
                (
                    v for v in versions
                    if (_v := parse_version(v)) and _v > version
                ),
                default=None
            ):
                container["image"] = (
                    f"{registry}/{user}/{image}:{newest_version}"
                )

                with open(path, "w") as file:
                    yaml.dump(container, file, sort_keys=False)

                repo.index.add([path])
                repo.git.commit(
                    "-m",
                    f"refactor({image}): update to {newest_version}",
                )

        # TODO: Support other registries.


if __name__ == "__main__":
    main()
