"""互換 shim — simulator.explore への委譲。"""

import sys

from simulator.explore import print_summary, run_grid_search

if __name__ == "__main__":
    if "--summary" in sys.argv:
        print_summary()
    else:
        run_grid_search()
        print_summary()
