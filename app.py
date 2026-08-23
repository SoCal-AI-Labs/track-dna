"""Launch the Track DNA desktop app."""

import os
from multiprocessing import freeze_support

for _key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_key, "1")

from trackdna.gui import main

if __name__ == "__main__":
    freeze_support()
    main()
