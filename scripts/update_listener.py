from argparse import ArgumentParser

import os
import sys
import fcntl
import pyinotify
import subprocess
import StringIO
import createrepo_updater

parser = ArgumentParser()

parser.add_argument("--queue-path", dest="queue_path", default="/tmp/upload/queue.txt")
parser.add_argument("--result-path", dest="result_path", default="result.txt")

args = parser.parse_args()

class QueueMonitor:
    wdd = None

    def __init__(self, queue_path, result_path):
        self.queue_path = queue_path
        self.result_path = result_path

        dirname = os.path.dirname(queue_path)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
            open(queue_path, 'a').close()
        elif not os.path.isfile(queue_path):
            open(queue_path, 'a').close()

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
        print('[%s] Checking queue...' % (createrepo_updater.stamp()))
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
                    sys.stderr.write('[%s] Ignoring invalid entry: %s\n' % (createrepo_updater.stamp(), q))
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
            print('[%s] Finished processing' % (createrepo_updater.stamp()))
        else:
            print('[%s] Queue is empty. Monitoring...' % (createrepo_updater.stamp()))

    def process(self, files, dest=None):
        print('[%s] Processing %d upload(s) for %s...' % (createrepo_updater.stamp(), len(files), dest or 'default repo'))
        repo_path = ['--repo-path', dest] if dest else []
        if dest is None:
            dest = '/mnt/storage/repos/smd-ros-building/fedora/linux'
        file_args = []
        #for f in files:
        #    file_args += ['-f', f]
        #cmd = ['python', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'include_folder.py'), '--invalidate', '-c'] + repo_path + file_args
        #try:
        #    out = 'Executing: ' + ' '.join(cmd) + '\n' + subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        #except subprocess.CalledProcessError, e:
        #    out = 'FAILED\nExecuting: %s\n%s' % (' '.join(cmd), e.output)
        #    sys.stderr.write('WARNING: Failed to process entry: %s\n' % (dest if dest else "default",))
        sio = StringIO.StringIO()
        try:
            pkgs = {}
            for folder in files:
                for root, dirs, dfiles in os.walk(folder):
                    for file in dfiles:
                        if file.endswith(".rpm"):
                            p = createrepo_updater.cr_package_from_file(os.path.join(root, file), sio)
                            sr = createrepo_updater.cr_determine_subrepo(p, log=sio)
                            sio.write('[%s] Determined that %s should go to %s\n' % (createrepo_updater.stamp(), os.path.basename(p.location_href), sr))
                            r = os.path.join(dest, sr)
                            if not r in pkgs:
                                pkgs[r] = set()
                            pkgs[r].add(p)

            for repo_base, packages in pkgs.items():
                package_names = set([p.name for p in packages])
                for p in packages:
                    parch = p.arch
                    break
                if not parch.lower() in ['src', 'source']:
                    createrepo_updater.cr_remove_downstream(repo_base, package_names, log=sio)
                createrepo_updater.cr_remove_pkg(repo_base, package_names, log=sio)
                createrepo_updater.cr_add_pkg(repo_base, packages, add_debuginfo=False, perform_relocate=True, copy=False, log=sio)

            createrepo_updater.cr_flush_all_pkg_list(sio)

            out = sio.getvalue()
        except Exception, e:
            out = 'FAILED\n%s%s' % (sio.getvalue(), e)
            sys.stderr.write('[%s] WARNING: Failed to process entry: %s\n' % (createrepo_updater.stamp(), dest if dest else "default",))
        for d in files:
            try:
                with open(os.path.join(d, self.result_path), 'w') as ffd:
                    ffd.write(out)
            except:
                sys.stderr.write('[%s] WARNING: Failed to write to result file: %s\n' % (createrepo_updater.stamp(), os.path.join(d, self.result_path),))

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
