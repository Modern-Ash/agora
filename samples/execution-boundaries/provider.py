import sys
import time


def main() -> None:
    mode = sys.argv[1]
    if mode == "sleep":
        time.sleep(5)
    elif mode == "flood":
        sys.stdout.write("x" * 100000)
        sys.stdout.flush()
    else:
        print('{"status":"ok"}')


if __name__ == "__main__":
    main()
