import sys
import subprocess
from urllib.parse import urlparse, parse_qs
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLineEdit, QPushButton, QComboBox, QLabel, QMessageBox, QProgressBar, QListWidget)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt5.QtGui import QColor, QPalette
import yt_dlp  # Still used for fetching formats

class FetchFormatsThread(QThread):
    completed = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                formats = info.get('formats', [])
            self.completed.emit(formats)
        except Exception as e:
            self.error.emit(str(e))

class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('YouTube Downloader')
        self.setGeometry(100, 100, 800, 600)
        self.start_time = None  # float seconds
        self.end_time = None  # float seconds
        self.time_segments = []  # List of (start, end) tuples
        self.video_id = None
        self.current_time = 0.0
        self.previewing = False
        self.player_ready = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_current_time)
        self.formats = []  # List of available formats
        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left panel: Time controls
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        # URL input
        left_panel.addWidget(QLabel('YouTube URL:'))
        self.url_input = QLineEdit()
        self.url_input.returnPressed.connect(self.load_video)
        left_panel.addWidget(self.url_input)
        load_btn = QPushButton('Load Video')
        load_btn.clicked.connect(self.load_video)
        left_panel.addWidget(load_btn)

        # Fetch formats button (still available for manual fetch)
        self.fetch_formats_btn = QPushButton('Fetch Formats')
        self.fetch_formats_btn.clicked.connect(self.start_fetch_formats)
        left_panel.addWidget(self.fetch_formats_btn)

        # Current time
        current_time_layout = QHBoxLayout()
        current_time_layout.addWidget(QLabel('current time:'))
        dec_btn = QPushButton('<')
        dec_btn.clicked.connect(lambda: self.adjust_time(-0.5))
        current_time_layout.addWidget(dec_btn)
        self.current_time_input = QLineEdit('0.0')
        self.current_time_input.setFixedWidth(50)
        self.current_time_input.returnPressed.connect(self.set_current_from_input)
        current_time_layout.addWidget(self.current_time_input)
        inc_btn = QPushButton('>')
        inc_btn.clicked.connect(lambda: self.adjust_time(0.5))
        current_time_layout.addWidget(inc_btn)
        left_panel.addLayout(current_time_layout)

        # Start and End buttons
        start_end_layout = QHBoxLayout()
        self.start_btn = QPushButton('start')
        self.start_btn.clicked.connect(self.set_start)
        start_end_layout.addWidget(self.start_btn)
        self.end_btn = QPushButton('end')
        self.end_btn.clicked.connect(self.set_end)
        start_end_layout.addWidget(self.end_btn)
        left_panel.addLayout(start_end_layout)

        # Start label
        self.start_label = QLabel('start: not set')
        left_panel.addWidget(self.start_label)

        # End label
        self.end_label = QLabel('end: not set')
        left_panel.addWidget(self.end_label)

        # Add segment button
        self.add_segment_btn = QPushButton('Add Segment')
        self.add_segment_btn.clicked.connect(self.add_segment)
        left_panel.addWidget(self.add_segment_btn)

        # Segments list
        self.segments_list = QListWidget()
        left_panel.addWidget(QLabel('Segments:'))
        left_panel.addWidget(self.segments_list)

        # Preview button
        self.preview_btn = QPushButton('preview')
        self.preview_btn.clicked.connect(self.preview_segment)
        left_panel.addWidget(self.preview_btn)

        # Download type
        left_panel.addWidget(QLabel('Download Type:'))
        self.download_type = QComboBox()
        self.download_type.addItems(['video', 'audio'])
        left_panel.addWidget(self.download_type)

        # Resolution mode
        left_panel.addWidget(QLabel('Resolution Mode:'))
        self.resolution_mode = QComboBox()
        self.resolution_mode.addItems(['highest', 'custom'])
        self.resolution_mode.currentTextChanged.connect(self.toggle_custom_format)
        left_panel.addWidget(self.resolution_mode)

        # Custom format (ComboBox)
        self.custom_format_label = QLabel('Custom Format:')
        self.custom_format = QComboBox()
        self.custom_format.setEnabled(False)
        left_panel.addWidget(self.custom_format_label)
        left_panel.addWidget(self.custom_format)

        # Cookies file input
        left_panel.addWidget(QLabel('Cookies File (optional):'))
        self.cookies_input = QLineEdit()
        left_panel.addWidget(self.cookies_input)

        # Download button
        self.download_btn = QPushButton('download')
        self.download_btn.clicked.connect(self.start_download)
        left_panel.addWidget(self.download_btn)

        # Progress bar (simple, since subprocess)
        self.progress_bar = QProgressBar()
        left_panel.addWidget(self.progress_bar)

        # Status
        self.status_label = QLabel('Ready')
        left_panel.addWidget(self.status_label)

        main_layout.addLayout(left_panel, 1)

        # Middle: Video preview
        self.video_view = QWebEngineView()
        self.video_view.setHtml('<html><body style="background-color: purple;"><h1 style="color: white;">Now Loading...</h1></body></html>')
        main_layout.addWidget(self.video_view, 3)

        # Apply purple theme
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(200, 162, 200))
        self.setPalette(palette)

    def toggle_custom_format(self, mode):
        enabled = mode == 'custom'
        self.custom_format.setEnabled(enabled)
        self.custom_format_label.setEnabled(enabled)
        if enabled and not self.formats:
            QMessageBox.information(self, 'Info', 'Please fetch formats first.')

    def start_fetch_formats(self):
        url = self.url_input.text()
        if not url:
            QMessageBox.warning(self, 'Error', 'Enter URL first')
            return
        self.fetch_thread = FetchFormatsThread(url)
        self.fetch_thread.completed.connect(self.update_formats)
        self.fetch_thread.error.connect(self.fetch_error)
        self.status_label.setText('Fetching formats...')
        self.fetch_thread.start()

    def update_formats(self, formats):
        self.formats = formats
        self.custom_format.clear()
        for fmt in self.formats:
            format_id = fmt.get('format_id', 'unknown')
            note = fmt.get('format_note', 'unknown')
            ext = fmt.get('ext', 'unknown')
            display = f"{format_id} - {note} ({ext})"
            self.custom_format.addItem(display, format_id)
        self.status_label.setText(f"Fetched {len(self.formats)} formats")

    def fetch_error(self, error):
        self.status_label.setText('Fetch failed')
        QMessageBox.critical(self, 'Error', f"{error}\nTry updating yt-dlp: pip install yt-dlp --upgrade")

    def load_video(self):
        url = self.url_input.text()
        try:
            parsed = urlparse(url)
            self.video_id = parse_qs(parsed.query)['v'][0]
            html = f"""
            <div id="player"></div>
            <script>
              var tag = document.createElement('script');
              tag.src = "https://www.youtube.com/iframe_api";
              var firstScriptTag = document.getElementsByTagName('script')[0];
              firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
              var player;
              function onYouTubeIframeAPIReady() {{
                player = new YT.Player('player', {{
                  height: '100%',
                  width: '100%',
                  videoId: '{self.video_id}',
                  playerVars: {{ 'enablejsapi': 1 }},
                  events: {{ 
                    'onReady': onPlayerReady,
                    'onStateChange': onPlayerStateChange 
                  }}
                }});
              }}
              function onPlayerReady(event) {{
                window.playerReady = true;
              }}
              function onPlayerStateChange(event) {{
              }}
            </script>
            """
            self.video_view.setHtml(html, QUrl(""))
            self.player_ready = False
            self.check_player_ready()
            self.status_label.setText('Loading video...')
            # Start fetching formats in parallel
            self.start_fetch_formats()
        except:
            QMessageBox.warning(self, 'Error', 'Invalid YouTube URL')

    def check_player_ready(self):
        self.video_view.page().runJavaScript("typeof window.playerReady !== 'undefined' && window.playerReady;", self.set_player_ready)

    def set_player_ready(self, ready):
        if ready:
            self.player_ready = True
            self.timer.start(100)
            self.status_label.setText('Video loaded and ready')
        else:
            QTimer.singleShot(500, self.check_player_ready)

    def update_current_time(self):
        if self.video_id and self.player_ready:
            js = """
            if (typeof player !== 'undefined' && typeof player.getCurrentTime === 'function') {
                player.getCurrentTime();
            } else {
                -1;
            }
            """
            self.video_view.page().runJavaScript(js, self.set_current_time)

    def set_current_time(self, time):
        if time is not None and time != -1:
            self.current_time = float(time)
            self.current_time_input.setText(f"{self.current_time:.1f}")
            if self.previewing and self.end_time is not None and self.current_time >= self.end_time:
                self.safe_pause_video()
                self.previewing = False
            # Duration not updated here since multi-segments

    def adjust_time(self, delta):
        if self.player_ready:
            new_time = self.current_time + delta
            self.safe_seek_to(new_time)

    def set_current_from_input(self):
        if self.player_ready:
            try:
                new_time = float(self.current_time_input.text())
                self.safe_seek_to(new_time)
            except:
                pass

    def safe_seek_to(self, time):
        js = f"""
        if (typeof player !== 'undefined' && typeof player.seekTo === 'function') {{
            player.seekTo({time}, true);
        }}
        """
        self.video_view.page().runJavaScript(js)

    def set_start(self):
        if self.player_ready:
            self.start_time = self.current_time
            self.start_label.setText(f"start: {self.format_time(self.start_time)}")

    def set_end(self):
        if self.player_ready:
            self.end_time = self.current_time
            self.end_label.setText(f"end: {self.format_time(self.end_time)}")

    def add_segment(self):
        if self.start_time is None or self.end_time is None or self.start_time >= self.end_time:
            QMessageBox.warning(self, 'Error', 'Invalid start/end times')
            return
        self.time_segments.append((self.start_time, self.end_time))
        self.segments_list.addItem(f"Segment: {self.format_time(self.start_time)} - {self.format_time(self.end_time)}")
        self.start_time = None
        self.end_time = None
        self.start_label.setText('start: not set')
        self.end_label.setText('end: not set')

    def preview_segment(self):
        if not self.player_ready:
            QMessageBox.warning(self, 'Error', 'Player not ready yet')
            return
        if self.start_time is None or self.end_time is None:
            QMessageBox.warning(self, 'Error', 'Set start and end times first')
            return
        self.previewing = True
        self.safe_seek_to(self.start_time)
        self.safe_play_video()

    def safe_play_video(self):
        js = """
        if (typeof player !== 'undefined' && typeof player.playVideo === 'function') {
            player.playVideo();
        }
        """
        self.video_view.page().runJavaScript(js)

    def safe_pause_video(self):
        js = """
        if (typeof player !== 'undefined' && typeof player.pauseVideo === 'function') {
            player.pauseVideo();
        }
        """
        self.video_view.page().runJavaScript(js)

    def start_download(self):
        if not self.url_input.text() or not self.time_segments:
            QMessageBox.warning(self, 'Error', 'Missing URL or segments')
            return
        mode = self.resolution_mode.currentText()
        if mode == 'custom' and self.custom_format.currentIndex() == -1:
            QMessageBox.warning(self, 'Error', 'Select a custom format')
            return

        self.download_btn.setEnabled(False)
        self.status_label.setText('Downloading...')
        self.progress_bar.setValue(0)

        url = self.url_input.text()
        cookies = self.cookies_input.text()
        download_type = self.download_type.currentText()
        custom_format_id = self.custom_format.currentData() if mode == 'custom' else None

        # Determine format string
        if mode == 'highest':
            format_str = 'best[height<=1080]' if download_type == 'video' else 'bestaudio'
        else:  # custom
            if download_type == 'video':
                format_str = f'{custom_format_id}+bestaudio/best'  # Merge video + audio
            else:
                format_str = custom_format_id

        try:
            for idx, (start, end) in enumerate(self.time_segments, 1):
                cmd = ['yt-dlp', url]
                if cookies:
                    cmd += ['--cookies', cookies]
                cmd += ['--download-sections', f'*{start}-{end}']
                cmd += ['-f', format_str]
                cmd += ['-o', f'output{idx}.%(ext)s']
                self.status_label.setText(f'Downloading segment {idx}...')
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(result.stderr)
                self.progress_bar.setValue(int((idx / len(self.time_segments)) * 100))
            self.status_label.setText('Download completed')
        except Exception as e:
            self.status_label.setText(f'Error: {str(e)}')
            QMessageBox.critical(self, 'Download Error', str(e))
        finally:
            self.download_btn.setEnabled(True)

    def format_time(self, seconds):
        if seconds is None:
            return 'not set'
        return f"{seconds:.1f}s"  # Simple seconds display for segments

def main():
    app = QApplication(sys.argv)
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()