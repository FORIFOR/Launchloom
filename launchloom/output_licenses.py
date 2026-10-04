"""License notices for exported Launchloom landing-page template code only."""
from importlib.resources import files
from pathlib import Path


LICENSE_FILES = ("LICENSE", "NOTICE")
TEMPLATE_MODIFICATION_NOTICE = (
    "Generated from Launchloom template code; modified with campaign content. "
    "See LICENSE and NOTICE for template licensing and scope."
)


def write_template_notices(destination: Path) -> None:
    # Package resources work in an installed wheel without a source checkout or
    # distribution-metadata lookup. Never copy the operator's campaign directory.
    resources = files("launchloom").joinpath("licenses")
    for name in LICENSE_FILES:
        (destination / name).write_bytes(resources.joinpath(name).read_bytes())
