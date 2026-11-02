import os
import sys
import threading
import time
import urllib.request
import webview
from django.core.management import execute_from_command_line

class DesktopApi:
    def download_file(self, url, default_filename):
        window = webview.windows[0]
        # Munculkan pop-up "Save As" Windows
        file_path = window.create_file_dialog(
            webview.SAVE_DIALOG, 
            directory='', 
            save_filename=default_filename,
            file_types=('Excel Files (*.xlsx)', 'All files (*.*)')
        )
        
        if file_path:
            target = file_path[0] if isinstance(file_path, (list, tuple)) else file_path
            # Unduh dan simpan file langsung dari server Django internal
            urllib.request.urlretrieve(url, target)
            return True
        return False

def start_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    execute_from_command_line(['manage.py', 'runserver', '127.0.0.1:8000', '--noreload'])

if __name__ == "__main__":
    django_thread = threading.Thread(target=start_django, daemon=True)
    django_thread.start()
    time.sleep(2)
    
    api_instance = DesktopApi()
    webview.create_window(
        title='Config Mesin Absensi', 
        url='http://127.0.0.1:8000',
        width=1024, 
        height=768,
        js_api=api_instance
    )
    webview.start()