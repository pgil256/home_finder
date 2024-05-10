import os
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class CeleryWatcher(FileSystemEventHandler):
    def __init__(self, command, path='.'):
        self.command = command
        self.restart()

    def restart(self):
        try:
            if self.process:
                self.process.kill()
        except AttributeError:
            pass
        self.process = subprocess.Popen(self.command, shell=True)

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"Changes detected in {event.src_path}. Restarting Celery...")
            self.restart()

if __name__ == "__main__":
    path = '.'  
    command = 'celery -A home_finder worker --loglevel=debug'  # Your Celery command
    event_handler = CeleryWatcher(command, path=path)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
