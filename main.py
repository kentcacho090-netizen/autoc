"""AutoC entry point for Termux."""
from runtime_patch import install_runtime_patches

install_runtime_patches()

from tui import main


if __name__ == "__main__":
    main()
