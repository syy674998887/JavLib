"""Command-line interface for JavLib."""

import argparse
import math
import os
import sys
from pathlib import Path

from .catalog import CONTENT_ID, FC2, STD_ID, list_folders, normalize
from .fetcher import (
    DEFAULT_IMAGE_DELAY,
    DEFAULT_PAGE_DELAY,
    DEFAULT_TITLE_DELAY,
    Fetcher,
)
from .rename import (
    default_journal,
    do_rename_folders,
    do_rename_videos,
    do_undo_folders,
    do_undo_videos,
)
from .scrape import do_inspect, do_scrape


DIR_ENV = "JAVLIB_DIR"


def catalog_number(value):
    """Parse a standalone catalog number, excluding filenames and paths."""
    value = value.strip()
    if not any(pattern.fullmatch(value) for pattern in (STD_ID, CONTENT_ID, FC2)):
        raise argparse.ArgumentTypeError(
            "expected a catalog number such as SONE-035, 3DSVR-1823 or FC2-PPV-1234567"
        )
    code, _ = normalize(value)
    return code


def non_negative_int(value):
    """Argparse type for counts where zero means unlimited."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return number


def non_negative_float(value):
    """Argparse type for finite delays where zero disables the wait."""
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite number 0 or greater")
    return number


def build_parser():
    parser = argparse.ArgumentParser(
        description="JavLib — JAV NAS media library builder "
        "(UGOS / Emby / Jellyfin / Kodi)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog="Run 'javlib COMMAND --help' for command-specific options.",
    )
    commands = parser.add_subparsers(
        dest="command", metavar="COMMAND", required=True, title="commands"
    )

    def command(name, help_text, description=None):
        return commands.add_parser(
            name,
            help=help_text,
            description=description or help_text,
            allow_abbrev=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

    def add_root(command_parser):
        command_parser.add_argument(
            "--dir",
            metavar="PATH",
            default=os.environ.get(DIR_ENV),
            help=f"media-library root (overrides {DIR_ENV})",
        )

    def add_selection(command_parser):
        command_parser.add_argument(
            "--limit",
            metavar="N",
            type=non_negative_int,
            default=0,
            help="process at most the first N folders after --only filtering "
            "(default 0 = all)",
        )
        command_parser.add_argument(
            "--only",
            metavar="NAME",
            action="append",
            default=[],
            help="select an exact, case-sensitive folder name (repeatable)",
        )

    def add_journal(command_parser, filename):
        command_parser.add_argument(
            "--journal",
            metavar="PATH",
            help=f"rollback journal (default <media-root>/{filename}, "
            "usable from any computer; reuse a custom path for undo)",
        )
        command_parser.set_defaults(journal_name=filename)

    scrape = command("scrape", "fetch metadata and write NFO/artwork")
    add_root(scrape)
    add_selection(scrape)

    get_command = command(
        "get", "scrape catalog numbers into output folders without local videos"
    )
    get_command.add_argument(
        "codes",
        metavar="CODE",
        nargs="+",
        type=catalog_number,
        help="one or more catalog numbers (for example SONE-035 IPVR-256)",
    )
    get_command.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default="output",
        help="destination root; creates one subfolder per code (default ./output)",
    )

    for scrape_parser in (scrape, get_command):
        scrape_parser.add_argument(
            "--force",
            action="store_true",
            help="re-scrape folders with movie.nfo and replace same-named generated files "
            "without touching video bytes",
        )
        scrape_parser.add_argument(
            "--page-delay",
            metavar="SECONDS",
            type=non_negative_float,
            default=DEFAULT_PAGE_DELAY,
            help=f"base page-request interval per source (default {DEFAULT_PAGE_DELAY:.1f}s; "
            "raised after HTTP 429/503)",
        )
        scrape_parser.add_argument(
            "--image-delay",
            metavar="SECONDS",
            type=non_negative_float,
            default=DEFAULT_IMAGE_DELAY,
            help=f"base image interval per host (default {DEFAULT_IMAGE_DELAY:.1f}s; "
            "raised after HTTP 429/503)",
        )
        scrape_parser.add_argument(
            "--delay",
            metavar="SECONDS",
            type=non_negative_float,
            default=DEFAULT_TITLE_DELAY,
            help=f"interval between networked titles (default {DEFAULT_TITLE_DELAY:.1f}s; "
            "no wait before the first title or for local skips)",
        )
        scrape_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="show request waits, inter-title waits, adaptive slowdown, and retries",
        )

    inspect = command(
        "inspect", "inspect catalog numbers and tags without network or writes"
    )
    add_root(inspect)
    add_selection(inspect)

    rename_folders = command(
        "rename-folders", "preview or apply normalized folder names"
    )
    add_root(rename_folders)
    add_selection(rename_folders)
    add_journal(rename_folders, "folder_rename_log.json")
    rename_folders.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed plan (default is preview only)",
    )

    rename_videos = command(
        "rename-videos",
        "preview or apply safe video and matching-sidecar filename cleanup",
    )
    add_root(rename_videos)
    add_selection(rename_videos)
    add_journal(rename_videos, "video_rename_log.json")
    rename_videos.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed plan (default is preview only)",
    )

    undo_folders = command(
        "undo-folders", "preview or apply the latest folder-rename rollback batch"
    )
    add_root(undo_folders)
    add_journal(undo_folders, "folder_rename_log.json")
    undo_folders.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed rollback plan (default is preview only)",
    )

    undo_videos = command(
        "undo-videos", "preview or apply the latest video-rename rollback batch"
    )
    add_root(undo_videos)
    add_journal(undo_videos, "video_rename_log.json")
    undo_videos.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed rollback plan (default is preview only)",
    )
    return parser


def parse_cli_args(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "get" and not args.dir:
        parser.error(f"specify the media root with --dir or set {DIR_ENV}")
    if "journal" in vars(args) and args.journal is None:
        args.journal = default_journal(args.dir, args.journal_name)
    return args


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = parse_cli_args()

    if args.command == "get":
        root = Path(args.output).expanduser()
        folders = [root / code for code in dict.fromkeys(args.codes)]
        try:
            for folder in folders:
                if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
                    raise OSError(f"output folder is occupied by a file or link: {folder}")
            root.mkdir(parents=True, exist_ok=True)
            for folder in folders:
                folder.mkdir(exist_ok=True)
        except OSError as error:
            sys.exit(f"Unable to prepare output directory: {error}")
        print(f"Output : {root.resolve()}")
        print(f"Titles : {len(folders)}")
    else:
        root = Path(args.dir).expanduser()
        if not root.is_dir():
            sys.exit(
                f"Directory does not exist or is not accessible: {root}\n"
                "Check the path, mount status, and permissions."
            )

        if args.command == "undo-folders":
            do_undo_folders(root, args.journal, apply=args.apply)
            return
        if args.command == "undo-videos":
            do_undo_videos(root, args.journal, apply=args.apply)
            return

        folders = list_folders(root)
        if args.only:
            selected = set(args.only)
            folders = [folder for folder in folders if folder.name in selected]
        if args.limit:
            folders = folders[: args.limit]

        if not folders:
            sys.exit("No folders found.")

        print(f"Root   : {root}")
        print(f"Folders: {len(folders)}")

        if args.command == "rename-folders":
            do_rename_folders(folders, args.journal, apply=args.apply)
            return
        if args.command == "rename-videos":
            do_rename_videos(folders, args.journal, apply=args.apply)
            return
        if args.command == "inspect":
            do_inspect(folders)
            return
        if args.command != "scrape":
            raise AssertionError(f"Unhandled command: {args.command}")

    fetcher = Fetcher(
        page_delay=args.page_delay,
        image_delay=args.image_delay,
        title_delay=args.delay,
        verbose=args.verbose,
    )
    return do_scrape(folders, fetcher, args)
