"""
devbench.py

A tool to measure the performance of developers and report, much like how
programs are performance measured.
"""

import os.path
import threading
import time
import random


EXIT_WORDS = ['q', 'quit', 'exit', 'abort']
OUT_FILE_NAME = 'dev.profile'
PRINT_DELAY_S = 2


# Writing only done in one thread, reading in another, synch not strictly
# required but screw it.
class DevBench(object):
    def __init__(self):
        self.lock = threading.Lock()

    def enter_process(self, name):
        self.lock.acquire()
        print('entering process %s' % name)

        self.lock.release()

    def leave_process(self):
        self.lock.acquire()
        print('leaving process...')

        self.lock.release()

    def report_str(self):
        self.lock.acquire()
        rv = ''
        self.lock.release()

        return rv


class DevPrinter(threading.Thread):
    def __init__(self, bench, delay, out_file):
        threading.Thread.__init__(self)
        self.bench = bench
        self.delay = delay
        self.out_file = out_file
        self.engaged = True
        self.daemon = True

    def run(self):
        while self.engaged:
            dir_name = os.path.dirname(os.path.abspath(self.out_file))
            if not os.path.isdir(dir_name):
                os.makedirs(dir_name)

            f = open(self.out_file, 'w')
            f.write('%s\n' % self.bench.report_str())
            f.close()
            time.sleep(self.delay)


def main():
    print(
'''\
DevBench engaged, q quit exit or abort [any caps] to exit.
Profiling is printed to %s, use python src/recat.py dev.profile to monitor.

USAGE:
    Enter Process/Subprocess:
        DevBench: >name_of_process

    Pop Out of Current Process:
        DevBench: <
''' % os.path.abspath(OUT_FILE_NAME))

    bench = DevBench()
    printer = DevPrinter(bench, PRINT_DELAY_S, OUT_FILE_NAME)
    printer.start()
    engaged = True
    while engaged:
        cmd = raw_input('DevBench: ')

        # Handle command
        cmd = cmd.lower()
        if cmd in EXIT_WORDS:
            engaged = False
            print('exiting...')
        elif cmd.startswith('>') and len(cmd) > 1:
            bench.enter_process(cmd[1:])
        elif cmd.startswith('<'):
            bench.leave_process()
        else:
            print('unrecognized command...')

    printer.engaged = False
    printer.join()

if __name__ == '__main__':
    main()
