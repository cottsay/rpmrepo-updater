from argparse import ArgumentParser

import os
import fcntl
import pyinotify
import shutil

parser = ArgumentParser()

parser.add_argument("--queue-path", dest="queue_path", default="/tmp/upload/queue.txt")
parser.add_argument("--result-path", dest="result_path", default="result.txt")
parser.add_argument("--repo-path", dest="repo_path", default=None)
# TODO: Handle multiple -f's
parser.add_argument("-f", dest="include_path")
parser.add_argument("--delete", dest="delete", action='store_true', default=False)

args = parser.parse_args()

result_path = os.path.join(args.include_path, args.result_path)
result_fd = open(result_path, 'w+')
wm = pyinotify.WatchManager()

class EventHandler(pyinotify.ProcessEvent):
    def my_init(self, fileobj, includepath):
        self._fileobj = fileobj
        self._includepath = includepath
    def process_default(self, event):
        outstr = self._fileobj.read()
        self._fileobj.close()
        print(outstr)
        if outstr.startswith('FAILED'):
            exit(1)
        if self._includepath:
            shutil.rmtree(self._includepath)
        exit(0)

handler = EventHandler(fileobj=result_fd, includepath=args.include_path if args.delete else None)
notifier = pyinotify.Notifier(wm, handler)
wdd = wm.add_watch(result_path, pyinotify.IN_MODIFY, rec=True)

print('Joining queue...')
with open(args.queue_path, 'a') as queue_fd:
    fcntl.lockf(queue_fd, fcntl.LOCK_EX)
    queue_fd.write(args.include_path)
    if(args.repo_path):
        queue_fd.write(' ' + args.repo_path)
    queue_fd.write('\n')
    fcntl.lockf(queue_fd, fcntl.LOCK_UN)

print('In queue. Waiting for report...')
notifier.loop()
