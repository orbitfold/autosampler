from .cli import cli


def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()

