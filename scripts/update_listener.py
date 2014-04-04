from argparse import ArgumentParser

import os
import sys
import fcntl
import pyinotify
import subprocess

parser = ArgumentParser()

parser.add_argument("--queue-path", dest="queue_path", default="/tmp/upload/queue.txt")
parser.add_argument("--result-path", dest="result_path", default="result.txt")

args = parser.parse_args()

class QueueMonitor:
    wdd = None

    def __init__(self, queue_path, result_path):
        self.queue_path = queue_path
        self.result_path = result_path
        self.fd = open(queue_path, 'r+')

        self.wm = pyinotify.WatchManager()

        handler = self.check_queue
        class EventHandler(pyinotify.ProcessEvent):
            def process_default(self, event):
                handler()

        self.handler = EventHandler()
        self.notifier = pyinotify.Notifier(self.wm, self.handler)
        self.wdd = self.wm.add_watch(self.queue_path, pyinotify.IN_DELETE, rec=True)
        self.start_monitor()

    def check_queue(self):
        # Check for pendig
        print('Checking queue...')
        fcntl.lockf(self.fd, fcntl.LOCK_EX)
        self.stop_monitor()
        raw_queue = self.fd.read().strip()
        self.fd.seek(0)
        self.fd.truncate()
        self.start_monitor()
        fcntl.lockf(self.fd, fcntl.LOCK_UN)
        queue = {}
        defqueue = []
        raw_queue = [tuple(l.split(' ')) for l in raw_queue.split('\n') if l]
        if raw_queue:
            for q in raw_queue:
                if len(q) > 2:
                    sys.stderr.write('Ignoring invalid entry: %s\n' % (q,))
                    continue
                if len(q) == 1:
                    defqueue.append(q[0])
                else:
                    if not q[1] in queue:
                        queue[q[1]] = []
                    queue[q[1]].append(q[0])
            if defqueue:
                self.process(defqueue)
            for k in queue.keys():
                self.process(queue[k], k)
            print('Finished processing')
        else:
            print('Queue is empty. Monitoring...')

    def process(self, files, dest=None):
        print('Processing %d files for %s...' % (len(files), dest or 'default'))
        try:
            repo_path = ['--repo-path', dest] if dest else []
            out = subprocess.check_output(['python', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'include_folder.py'), '--invalidate', '-c'] + repo_path + ['-f'] + files, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError, e:
            out = 'FAILED\n%s' % (e.output,)
            sys.stderr.write('WARNING: Failed to process entry: %s\n' % (dest if dest else "default",))
        for d in files:
            try:
                with open(os.path.join(d, self.result_path), 'w') as ffd:
                    ffd.write(out)
            except:
                pass

    def start_monitor(self):
        if self.wdd[self.queue_path] > 0:
            self.wm.update_watch(self.wdd[self.queue_path], mask=pyinotify.IN_MODIFY)

    def stop_monitor(self):
        if self.wdd[self.queue_path] > 0:
            self.wm.update_watch(self.wdd[self.queue_path], mask=pyinotify.IN_DELETE)

    def loop(self):
        self.check_queue()
        self.notifier.loop()
   

qmon = QueueMonitor(args.queue_path, args.result_path)
qmon.loop()
