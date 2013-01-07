"""
devbench.py

A tool to measure the performance of developers and report, much like how
programs are performance measured.
"""

import sys
import os.path
import threading
import time
import StringIO
import json


EXIT_WORDS = ['q', 'quit', 'exit', 'abort']
DEFAULT_PROJECT = time.strftime('bench_%b_%d_%Y')
PRINT_DELAY_S = 0.25


def time_str(time_s):
    sec_i = int(time_s)

    # More than 1 minute, count minutes
    if sec_i >= 60:
        min_i = sec_i / 60
        sec_i -= min_i * 60
        time_s -= min_i * 60

        # More than an hour, count hours
        if min_i >= 60:
            hr_i = min_i / 60
            min_i -= hr_i * 60

            # More than 1 day, count days
            if hr_i >= 24:
                day_i = hr_i / 24
                hr_i -= day_i * 24
                rv = '%d d, %d h, %d m, %.2f s' % (
                    day_i, hr_i, min_i, time_s
                )

            # Less than 1 day, print hr:min:sec
            else:
                rv = '%d h, %d m, %.2f s' % (hr_i, min_i, time_s)

        # Less than an hour has passed, pring min:sec
        else:
            rv = '%d m, %.2f s' % (min_i, time_s)

    # Less than 1 minute, simply print seconds
    else:
        rv = '%.2f s' % time_s

    return '[%s]' % rv


class Process(object):
    def __init__(self, name, parent):
        self.parent = parent
        self.children = list()
        self.begin_time = time.time()
        self.name = name.lower()
        self.end_time = -1
        self.personal_time = 0
        self.total_time = 0

    def __str__(self):
        return '<Process %s>' % self.name

    def __repr__(self):
        return str(self)

    def _add_time(self, t):
        self.personal_time += t
        self.total_time += t

    def ended(self):
        return self.end_time != -1

    def time_so_far(self):
        now = time.time()
        if not self.ended():
            return now - self.begin_time

        raise RuntimeError('cannot be called on ended process')

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

    @staticmethod
    def _json_object_hook(dct):
        proc = Process('', None)
        proc.name = dct['name']
        proc.begin_time = dct['begin_time']
        proc.end_time = dct['end_time']
        proc.personal_time = dct['personal_time']
        proc.total_time = dct['total_time']
        proc.children = dct['children']
        for child in proc.children:
            child.parent = proc
        if proc.name == 'root':
            proc.end_time = -1
            proc.parent = None
        return proc


class ProcessEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Process):
            return {
                'name': obj.name,
                'begin_time': obj.begin_time,
                'end_time': obj.end_time,
                'personal_time': obj.personal_time,
                'total_time': obj.total_time,
                'children': [self.default(child) for child in obj.children]
            }
        return json.JSONEncoder.default(self, obj)


# Writing only done in one thread, reading in another, synch not strictly
# required but screw it.
class DevBench(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.root = Process('root', None)

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

    def running_process(self):
        self.lock.acquire()
        proc = self.root
        rv = proc
        while proc:
            if len(proc.children) and not proc.children[-1].ended():
                proc = proc.children[-1]
                rv = proc
            else:
                proc = None
        self.lock.release()
        return rv

    def running_path(self):
        self.lock.acquire()
        out = StringIO.StringIO()
        proc = self.root
        while proc:
            out.write(proc.name)
            if len(proc.children) and not proc.children[-1].ended():
                out.write('.')
                proc = proc.children[-1]
            else:
                proc = None
        self.lock.release()
        return out.getvalue()

    def report_str(self):
        self.lock.acquire()
        out = StringIO.StringIO()
        avgs = dict()
        depth = 0
        proc = self.root
        while proc:
            if not proc.ended():
                format = '%s%s (Running... personal: %s, total: %s):\n'
            else:
                format = '%s%s (Ended personal: %s, total: %s):\n'
            out.write(format % (
                '  ' * depth, proc.name, time_str(proc.personal_time), time_str(proc.total_time)
            ))

            if proc.name not in avgs:
                avgs[proc.name] = list()
            avgs[proc.name].append(proc)

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

        # If not done, write running time
        cur_proc = self.running_process()
        if not cur_proc.ended():
            out.write('\ncurrent: %s, time so far: %s' % (
                self.running_path(), time_str(cur_proc.time_so_far())
            ))

        # Otherwise, write out time by process
        else:
            for k, v in avgs.items():
                num_procs = len(v)
                total_ptime = 0
                total_ttime = 0
                for proc in v:
                    total_ptime += proc.personal_time
                    total_ttime += proc.total_time
                avgs[k] = (total_ptime, total_ttime, total_ptime / num_procs, total_ttime / num_procs, num_procs)

            avgs = sorted(avgs.items())

            out.write('\nProcesses By Name:\n')
            for itm in avgs:
                out.write('%s: tot_prs: %s, tot_tot: %s, avg_prs: %s, avg_tot: %s, occurrences: %d\n' %
                    ((itm[0], ) + tuple([time_str(n) for n in itm[1][:-1]]) + (itm[1][-1], ))
                )
        self.lock.release()
        return out.getvalue()

    def loadf(self, file):
        self.lock.acquire()
        self.root = json.load(file, object_hook=Process._json_object_hook)
        self.lock.release()

    def savef(self, file):
        self.lock.acquire()
        json.dump(self.root, file, cls=ProcessEncoder, indent=2, separators=(',', ': '))
        self.lock.release()


class DevPrinter(threading.Thread):
    def __init__(self, bench, delay, out_file_name, session_file_name):
        threading.Thread.__init__(self)
        self.bench = bench
        self.delay = delay
        self.out_file_name = out_file_name
        self.session_file_name = session_file_name
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
            f = open(self.out_file_name, 'w')
            f.write('%s\n' % self.bench.report_str())
            f.close()
            f = open(self.session_file_name, 'w')
            self.bench.savef(f)
            f.close()
            time.sleep(self.delay)


def main():
    project = DEFAULT_PROJECT
    out_file_name = os.path.join(project, 'out')
    session_file_name = os.path.join(project, 'bench.json')
    if len(sys.argv) > 1:
        project = sys.argv[1]
        out_file_name = os.path.join(project, 'out')
        session_file_name = os.path.join(project, 'bench.json')

    if not os.path.isdir(project):
        try:
            os.makedirs(project)
        except:
            raise RuntimeError('failed to create project directory %s' % project)

    def test_open(file_name, mode):
        try:
            existed = os.path.isfile(file_name)
            if existed or 'r' not in mode:
                f = open(file_name, mode)
                f.close()
                if not existed:
                    os.remove(file_name)
        except:
            raise RuntimeError('could not open %s for writing, exiting...' % file_name)
    test_open(out_file_name, 'r')
    test_open(session_file_name, 'r')

    print(
'''\
DevBench engaged, q quit exit or abort [any caps] to exit.
Profiling project %s. Printing to %s/out, use python src/recat.py %s/out to monitor.

USAGE:
    Enter Process/Subprocess:
        DevBench: name_of_process

    Pop Out of Current Process:
        DevBench: <
''' % (project, project, project))

    bench = DevBench()

    # Can we continue session?
    if os.path.isfile(session_file_name):
        bench.loadf(open(session_file_name))

    # Test write
    test_open(out_file_name, 'w')
    test_open(session_file_name, 'w')

    # Engage printer
    printer = DevPrinter(bench, PRINT_DELAY_S, out_file_name, session_file_name)
    printer.start()
    engaged = True
    while engaged:
        cmd = raw_input('DevBench (%s): ' % bench.running_path())

        # Handle command
        cmd = cmd.lower()
        if cmd in EXIT_WORDS:
            engaged = False
            print('exiting...')
        elif not cmd.startswith('<') and len(cmd) > 0:
            print('entering process %s' % cmd)
            bench.enter_process(cmd)
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
