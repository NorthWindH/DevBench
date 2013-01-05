"""
recat.py

Auxilliary printer for output file. Will reprint file as it is modified. Meant
to be used with dev.profile.
"""

import sys
import os.path
import time


if __name__ == '__main__':
    f_path = sys.argv[1] if len(sys.argv) > 1 else ''
    if os.path.isfile(f_path):
        last_mt = os.path.getmtime(f_path)
        while True:
            new_mt = os.path.getmtime(f_path)
            if new_mt > last_mt:
                print('Reprint:')
                last_mt = new_mt
                f = open(f_path)
                for line in f.readlines():
                    print(line)
            time.sleep(1)
