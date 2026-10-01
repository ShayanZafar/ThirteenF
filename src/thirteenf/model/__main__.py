"""python -m thirteenf.model rebuilds the model tables from the raw SEC tables."""

from thirteenf.model.build import build_all

if __name__ == "__main__":
    build_all()
