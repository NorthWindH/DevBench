"""
devbench.py

A tool to measure the performance of developers and report, much like how
programs are performance measured.
"""

import os.path
import threading
import time
import StringIO


EXIT_WORDS = ['q', 'quit', 'exit', 'abort']
OUT_FILE_NAME = 'dev.profile'
PRINT_DELAY_S = 2


class Process(object):
    def __init__(self, name, parent):
        self.parent = parent
        self.children = list()
        self.begin_time = time.time()
        self.name = name
        self.end_time = -1
        self.personal_time = 0
        self.total_time = 0

    def __str__(self):
        return '<Process %s>' % self.name

    def __repr__(self):
        return str(self)

    def ended(self):
        return self.end_time != -1

    def _add_time(self, t):
        self.personal_time += t
        self.total_time += t

    def begin(self, name):
        # Ensure we are not already ended
        if self.ended():
            raise RuntimeError('cannot begin into already ended process %s' % self.name)

        # No children, append to personal time, add child
        if not len(self.children):
            new_child = Process(name, self)
            self._add_time(new_child.begin_time - self.begin_time)
            self.children.append(new_child)

        # Last child ended, add to personal time, add child
        elif self.children[-1].ended():
            new_child = Process(name, self)
            self._add_time(new_child.begin_time - self.children[-1].end_time)
            self.children.append(new_child)

        # Last child still not ended, propagate begin
        else:
            self.children[-1].begin(name)

    def end(self):
        # No children or all children ended, add time, set end time
        if not len(self.children):
            self.end_time = time.time()
            self._add_time(self.end_time - self.begin_time)

        elif self.children[-1].ended():
            self.end_time = time.time()
            self._add_time(self.end_time - self.children[-1].end_time)

        # Last child still not ended, propagate end
        else:
            last_child = self.children[-1]
            ended_process = last_child.end()

            # Did last child end as result? Add to total time
            if last_child.ended():
                self.total_time += last_child.total_time

            return ended_process
        return self.name


# Writing only done in one thread, reading in another, synch not strictly
# required but screw it.
class DevBench(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.root = Process('Root', None)

    def done(self):
        return self.root.ended()

    def enter_process(self, name):
        self.lock.acquire()
        self.root.begin(name)
        self.lock.release()

    def leave_process(self):
        self.lock.acquire()
        ended_process = self.root.end()
        self.lock.release()
        return ended_process

    def report_str(self):
        self.lock.acquire()
        out = StringIO.StringIO()
        depth = 0
        proc = self.root
        while proc:
            if not proc.ended():
                format = '%s%s (Running... personal: %f, total: %f):\n'
            else:
                format = '%s%s (Ended personal: %f, total: %f):\n'
            out.write(format % (
                '  ' * depth, proc.name, proc.personal_time, proc.total_time
            ))

            # Attempt to descend
            if len(proc.children):
                proc = proc.children[0]
                depth += 1

            # Cannot descend, ascend
            else:
                while proc.parent:
                    index = proc.parent.children.index(proc) + 1

                    # Sibling?
                    if index < len(proc.parent.children):
                        proc = proc.parent.children[index]
                        break

                    # No sibling, jump up again
                    else:
                        depth -= 1
                        proc = proc.parent

                # No parent, done
                else:
                    proc = None
        self.lock.release()
        return out.getvalue()


class DevPrinter(threading.Thread):
    def __init__(self, bench, delay, out_file):
        threading.Thread.__init__(self)
        self.bench = bench
        self.delay = delay
        self.out_file = out_file
        self.engaged_lock = threading.Lock()
        self.engaged_count = -1
        self.daemon = True

    def terminate(self):
        self.engaged_lock.acquire()
        self.engaged_count = 2
        self.engaged_lock.release()

    def can_loop(self):
        self.engaged_lock.acquire()
        if self.engaged_count == -1:
            rv = True
        else:
            self.engaged_count -= 1
            rv = self.engaged_count > 0
        self.engaged_lock.release()
        return rv

    def run(self):
        while self.can_loop():
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
            name = cmd[1:]
            print('entering process %s' % name)
            bench.enter_process(name)
        elif cmd.startswith('<'):
            print('leaving process %s...' % bench.leave_process())
            if bench.root.ended():
                print('all processes ended, exiting...')
                engaged = False
        else:
            print('unrecognized command...')

    while not bench.done():
        bench.leave_process()

    printer.terminate()
    printer.join()

if __name__ == '__main__':
    main()
