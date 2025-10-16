import sys
import os
import subprocess
from urllib.parse import urlparse, parse_qs
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLineEdit, QPushButton, QComboBox, QLabel, QMessageBox, QProgressBar, QListWidget, QFileDialog)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
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
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'skip': ['dash', 'hls']}}  # Skip problematic manifests to avoid nsig issues
            }
            # Check for cookies.txt in current directory
            cookies_file = 'cookies.txt'
            if os.path.exists(cookies_file):
                ydl_opts['cookiefile'] = cookies_file
            else:
                ydl_opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
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
        self.setGeometry(100, 100, 1800, 600)
        self.start_time = None  # float seconds
        self.end_time = None  # float seconds
        self.time_segments = []  # List of (start, end) tuples
        self.video_id = None
        self.current_time = 0.0
        self.previewing = False
        self.player_ready = False
        self.download_dir = os.getcwd()  # Default to current directory
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_current_time)
        self.formats = []  # List of available formats
        self.is_fetching = False  # Flag to track fetching status
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

        # Fetch formats button
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

        # Segments list and delete button
        segments_layout = QHBoxLayout()
        self.segments_list = QListWidget()
        self.segments_list.setSelectionMode(QListWidget.ExtendedSelection)  # Allow multiple selection
        self.segments_list.setMinimumWidth(400)  # Increased width
        segments_layout.addWidget(self.segments_list)
        delete_segment_btn = QPushButton('Delete Segment')
        delete_segment_btn.clicked.connect(self.delete_selected_segment)
        segments_layout.addWidget(delete_segment_btn)
        left_panel.addWidget(QLabel('Segments:'))
        left_panel.addLayout(segments_layout)

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

        # Download directory
        left_panel.addWidget(QLabel('Download Directory:'))
        self.download_dir_label = QLabel(self.download_dir)
        left_panel.addWidget(self.download_dir_label)
        choose_dir_btn = QPushButton('Choose Download Directory')
        choose_dir_btn.clicked.connect(self.choose_download_dir)
        left_panel.addWidget(choose_dir_btn)

        # Download button
        self.download_btn = QPushButton('download')
        self.download_btn.clicked.connect(self.start_download)
        left_panel.addWidget(self.download_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        left_panel.addWidget(self.progress_bar)

        # Status
        self.status_label = QLabel('Ready')
        left_panel.addWidget(self.status_label)

        main_layout.addLayout(left_panel, 1)

        # Middle: Video preview
        self.video_view = QWebEngineView()
        # Set up page to enable JavaScript
        self.video_page = QWebEnginePage(self.video_view)
        self.video_view.setPage(self.video_page)
        self.video_page.settings().setAttribute(self.video_page.settings().JavascriptEnabled, True)
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
        if enabled and not self.formats and not self.is_fetching:
            QMessageBox.information(self, 'Info', 'Please fetch formats first.')

    def start_fetch_formats(self):
        url = self.url_input.text()
        if not url:
            QMessageBox.warning(self, 'Error', 'Enter URL first')
            return
        self.is_fetching = True
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
        self.is_fetching = False
        self.status_label.setText(f"Fetched {len(self.formats)} formats")

    def fetch_error(self, error):
        self.is_fetching = False
        self.status_label.setText('Fetch failed')
        QMessageBox.critical(self, 'Error', f"{error}\nTry updating yt-dlp: pip install yt-dlp --upgrade")

    def load_video(self):
        url = self.url_input.text()
        try:
            parsed = urlparse(url)
            self.video_id = parse_qs(parsed.query)['v'][0]
            # Use direct iframe embed with explicit IFrame API script
            embed_url = f"https://www.youtube.com/embed/{self.video_id}?enablejsapi=1&origin=*&referrerPolicy=no-referrer-when-downgrade&playsinline=1"
            html = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <meta http-equiv="Content-Security-Policy" content="default-src 'self' https://www.youtube.com https://youtube.com https://*.youtube.com; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.youtube.com https://youtube.com https://*.youtube.com https://www.google.com; frame-src https://www.youtube.com https://youtube.com https://*.youtube.com; connect-src 'self' https://www.youtube.com https://youtube.com https://*.youtube.com">
                <style>body {{ margin: 0; padding: 0; background-color: purple; }} #player {{ width: 100%; height: 100%; }}</style>
                <script src="https://www.youtube.com/iframe_api"></script>
            </head>
            <body>
                <div id="player"></div>
                <script>
                    var player;
                    function onYouTubeIframeAPIReady() {{
                        player = new YT.Player('player', {{
                            height: '100%',
                            width: '100%',
                            videoId: '{self.video_id}',
                            playerVars: {{ 'enablejsapi': 1, 'origin': '*' }},
                            events: {{ 'onReady': onPlayerReady }}
                        }});
                    }}
                    function onPlayerReady(event) {{
                        window.playerReady = true;
                        console.log('Player ready');
                    }}
                </script>
            </body>
            </html>
            """
            self.video_view.setHtml(html, QUrl("https://localhost"))  # Use https scheme to satisfy secure context
            self.player_ready = False
            self.check_player_ready()
            self.status_label.setText('Loading video...')
            self.start_fetch_formats()
        except Exception as e:
            self.status_label.setText('Load failed')
            QMessageBox.warning(self, 'Error', f'Invalid YouTube URL: {str(e)}')

    def check_player_ready(self):
        if self.video_id:
            js = "typeof window.playerReady !== 'undefined' && window.playerReady;"
            self.video_view.page().runJavaScript(js, self.set_player_ready)

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

    def delete_selected_segment(self):
        selected_items = self.segments_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, 'Error', 'Please select at least one segment to delete')
            return
        for item in selected_items:
            segment_text = item.text()
            start_end = segment_text.replace('Segment: ', '').split(' - ')
            start = float(start_end[0].replace('s', ''))
            end = float(start_end[1].replace('s', ''))
            segment_to_remove = (start, end)
            if segment_to_remove in self.time_segments:
                self.time_segments.remove(segment_to_remove)
            self.segments_list.takeItem(self.segments_list.row(item))

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

    def choose_download_dir(self):
        dir = QFileDialog.getExistingDirectory(self, "Select Download Directory", self.download_dir)
        if dir:
            self.download_dir = dir
            self.download_dir_label.setText(self.download_dir)

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
                cmd += ['-o', os.path.join(self.download_dir, f'output{idx}.%(ext)s')]
                self.status_label.setText(f'Downloading segment {idx}...')
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(result.stderr)
                self.progress_bar.setValue(int((idx / len(self.time_segments)) * 100))
            self.status_label.setText('Download completed')
            # Clear segments after successful download
            self.time_segments.clear()
            self.segments_list.clear()
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