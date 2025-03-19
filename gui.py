from bot import *
from PyQt6.QtGui import *
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
import sys
import json
import os
import qasync
from io import StringIO
import logging
import shutil

# Create our custom stderr that redirects to logging
class LoggedStderr:
    def write(self, msg):
        if msg.strip():  # Only log non-empty messages
            stderr_logger.error(msg)
    
    def flush(self):
        pass

# Centralized logging setup
def setup_logging():
    logging.basicConfig(
        filename='bot.log',
        filemode='w',
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: logging.error(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
    )
    sys.stderr = LoggedStderr()

setup_logging()

# Create a logger for stderr
stderr_logger = logging.getLogger('stderr')
stderr_logger.setLevel(logging.DEBUG)

sys.stderr = LoggedStderr()

default_config_dict = {
    "bot_token": "",
    "ACTIVE_MATCHES_CHANNEL_ID": "",
    "REPORTED_MATCHES_CHANNEL_ID": "",
    "total_dans": 7,
    "minimum_derank": 2,
    "maximum_rank_difference": 1,
    "rank_gap_for_more_points": 1,
    "point_rollover": True,
    "queue_status": True
}

# Utility functions for configuration management
def load_config(file_path, default_config):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return default_config

def save_config(file_path, config):
    with open(file_path, 'w') as f:
        json.dump(config, f, indent=4)

class MainTab(QWidget):
    def __init__(self, bot):
        super().__init__()

        # Create and configure logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        layout = QVBoxLayout(self)

        # Create status label to show current state
        self.status_label = QLabel("Current State: Stopped\n(Make sure you have a valid token in the config!)")
        layout.addWidget(self.status_label)

        #Add Main Content
        self.start_bot_button = QPushButton(text="Start the Bot")
        self.start_bot_button.setCheckable(True)
        self.start_bot_button.clicked.connect(self.on_button_clicked)

        layout.addWidget(self.start_bot_button)

        self.is_running = False

        self.bot = bot

    def on_button_clicked(self):
        self.is_running = self.start_bot_button.isChecked()
        if self.is_running:
            asyncio.create_task( self.start_bot())
            self.start_bot_button.setText("Stop")
            self.status_label.setText("Current State: Running")
        else:
            asyncio.create_task( self.stop_bot())
            self.start_bot_button.setText("Start")
            self.status_label.setText("Current State: Stopped")

    async def start_bot(self):
        self.logger.info("start_bot")
        try:
            config = load_config("config.json", default_config_dict)
            token = config['bot_token']
            await self.bot.start(token)
        except Exception as e:
            self.logger.error(f"Failed to start bot: {str(e)}")

    async def stop_bot(self):
        self.logger.info("stop_bot")
        await self.bot.close()

class ConfigTab(QWidget):
    def __init__(self, bot):
        super().__init__()

        self.bot = bot
        layout = QVBoxLayout(self)
        self.config_form_layout = QFormLayout()

        #create fields for the form
        self.bot_token = QLineEdit()
        self.bot_token.setPlaceholderText("Enter your Discord Bot Token")

        self.ACTIVE_MATCHES_CHANNEL_ID = QLineEdit()
        self.ACTIVE_MATCHES_CHANNEL_ID.setPlaceholderText("Enter the discord channel id where you want the bot to post match messages")

        self.REPORTED_MATCHES_CHANNEL_ID = QLineEdit()
        self.REPORTED_MATCHES_CHANNEL_ID.setPlaceholderText("Enter the discord channel id where you want the bot to report match results")

        self.total_dans = QSpinBox()
        self.total_dans.setRange(1, 12)
        self.total_dans.setValue(7)

        #you cannot derank below self.minimum_derank
        self.minimum_derank = QSpinBox()
        self.minimum_derank.setRange(1,12)
        self.minimum_derank.setValue(2)

        #you cannot gain points beating someone who is maximum_rank_difference below you in rank
        self.maximum_rank_difference = QSpinBox()
        self.maximum_rank_difference.setRange(1,11)
        self.maximum_rank_difference.setValue(2)

        self.rank_gap_for_more_points = QSpinBox()
        self.rank_gap_for_more_points.setRange(1,11)
        self.rank_gap_for_more_points.setValue(1)

        self.point_rollover = QCheckBox()
        self.point_rollover.setToolTip("whether point gains roll over on rank up")

        self.queue_status = QCheckBox()
        self.queue_status.setToolTip("whether matchmaking queue is enabled/disabled")

        #Adding fields to form
        self.config_form_layout.addRow("Bot Token:", self.bot_token)
        self.config_form_layout.addRow("Active Match Channel Id:", self.ACTIVE_MATCHES_CHANNEL_ID)
        self.config_form_layout.addRow("Reported Match Channel Id:", self.REPORTED_MATCHES_CHANNEL_ID)
        self.config_form_layout.addRow("Total Dans:", self.total_dans)
        self.config_form_layout.addRow("Minimum Derank:", self.minimum_derank)
        self.config_form_layout.addRow("Maximum Rank Difference:", self.maximum_rank_difference)
        self.config_form_layout.addRow("Rank Gap for More Points:", self.rank_gap_for_more_points)

        #add checkboxes
        self.config_form_layout.addRow("Point Rollover:",  self.point_rollover)
        self.config_form_layout.addRow("Matchmaking Queue Status",  self.queue_status)
        
        layout.addLayout(self.config_form_layout)

        # Create save/load buttons
        self.button_layout = QVBoxLayout()
        self.save_button = QPushButton("Save Configuration")
        self.load_button = QPushButton("Load Configuration")
        self.save_button.clicked.connect(self.save_config)
        self.load_button.clicked.connect(self.load_config)
        self.button_layout.addWidget(self.save_button)
        self.button_layout.addWidget(self.load_button)

        #add buttons to layout
        layout.addLayout(self.button_layout)

        self.settings_file = "config.json"
        self.load_config()

    def get_config_dict(self):
        """Get current configuration as a dictionary"""
        return {
            #Text
            "bot_token" : self.bot_token.text(),
            "ACTIVE_MATCHES_CHANNEL_ID" : self.ACTIVE_MATCHES_CHANNEL_ID.text(),
            "REPORTED_MATCHES_CHANNEL_ID" : self.REPORTED_MATCHES_CHANNEL_ID.text(),
            #Numbers
            "total_dans" : self.total_dans.value(),
            "minimum_derank" : self.minimum_derank.value(),
            "maximum_rank_difference" : self.maximum_rank_difference.value(),
            "rank_gap_for_more_points" : self.rank_gap_for_more_points.value(),
            #Bools
            "point_rollover" : self.point_rollover.isChecked(),
            "queue_status" :  self.queue_status.isChecked()
        }

    def set_config_dict(self, config):
        """Set configuration from a dictionary"""
        #Text
        self.bot_token.setText(config.get("bot_token", ""))
        self.ACTIVE_MATCHES_CHANNEL_ID.setText(config.get("ACTIVE_MATCHES_CHANNEL_ID", ""))
        self.REPORTED_MATCHES_CHANNEL_ID.setText(config.get("REPORTED_MATCHES_CHANNEL_ID", ""))
        #Numbers
        self.total_dans.setValue(config.get("total_dans", 7))
        self.minimum_derank.setValue(config.get("minimum_derank", 2))
        self.maximum_rank_difference.setValue(config.get("maximum_rank_difference", 1))
        self.rank_gap_for_more_points.setValue(config.get("rank_gap_for_more_points", 1))
        #Bools
        self.point_rollover.setChecked(config.get("point_rollover", True))
        self.queue_status.setChecked(config.get("queue_status", True))

    def save_config(self):
        """Save configuration to file"""
        try:
            config = self.get_config_dict()
            save_config(self.settings_file, config)

            update_bot_config(self.bot)
            QMessageBox.information(self, "Success", "Configuration saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {str(e)}")
    
    def load_config(self):
        """Load configuration from file"""
        try:
            config = load_config(self.settings_file, default_config_dict)
            self.set_config_dict(config)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to load configuration: {str(e)}")

class ColoredQTextEditLogger(logging.Handler):
    COLORS = {
        logging.DEBUG: 'black',
        logging.INFO: 'blue',
        logging.WARNING: 'orange',
        logging.ERROR: 'red',
        logging.CRITICAL: 'purple'
    }

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.setReadOnly(True)
        format_string = '%(asctime)s - %(levelname)s - %(message)s'
        self.setFormatter(logging.Formatter(format_string))

    def emit(self, record):
        color = self.COLORS.get(record.levelno, 'black')
        msg = self.format(record)
        html = f'<span style="color: {color};">{msg}</span>'
        self.text_widget.append(html)

class LogTab(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        self.config_form_layout = QFormLayout()

        # Create and configure logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        # Create text display
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        layout.addWidget(self.text_display)

        # Configure the root logger instead of creating a new one
        root_logger = logging.getLogger()  # Get the root logger
        root_logger.setLevel(logging.INFO)

        self.logs_handler = ColoredQTextEditLogger(self.text_display)
        root_logger.addHandler(self.logs_handler)

        #Add Main Content
        self.save_logs_button = QPushButton(text="Save Logs")
        self.save_logs_button.clicked.connect(self.save_logs)

        layout.addWidget(self.save_logs_button)
    
    def save_logs(self):
        text = self.text_display.toPlainText()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output",
            "",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(text)
                self.logger.info(f"Output saved to {file_path}")
            except Exception as e:
                self.logger.error(f"Error saving file: {str(e)}")

class AdminTab(QWidget):
    def __init__(self,con):
        super().__init__()
        self.con = con

        # Create and configure logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        layout = QVBoxLayout(self)
        # Create a button to trigger the save file dialog
        self.reset_season_button = QPushButton('Reset Danisen for new season\n(will backup danisen db file)', self)
        self.reset_season_button.clicked.connect(self.reset_season)

        layout.addWidget(self.reset_season_button)
    def reset_season(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output",
            "",
            "Database Files (*.db);;All Files (*)"
        )
        if file_path:
            try:
                shutil.copy("danisen.db", file_path)
                self.logger.info(f"danisen.db file copied to {file_path}")
                self._reset_player_data()
            except Exception as e:
                self.logger.error(f"Failed to reset season: {str(e)}")

    def _reset_player_data(self):
        cursor = self.con.cursor()
        cursor.execute("""
            UPDATE players
            SET dan = ?, points = ?
        """, (1, 0))
        self.con.commit()
        self.logger.info("Player data reset successfully.")

class DanisenWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.con = sqlite3.connect("danisen.db")

        # Create and configure logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        #Create config file if non-existant
        self.settings_file = "config.json"
        if not os.path.exists(self.settings_file):
            save_config(self.settings_file, default_config_dict)

        #Creating DanisenBot
        self.bot = create_bot(self.con)

        self.setWindowTitle("Danisen Bot")
        self.setMinimumSize(600, 400)

        # Create the central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Tab widget
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)

        # Add Tabs
        tabs.addTab(MainTab(self.bot), "Main")
        tabs.addTab(ConfigTab(self.bot), "Config")
        tabs.addTab(LogTab(), "Logs")
        tabs.addTab(AdminTab(self.con), "Admin")
        #TODO tabs.addTab(self.create_logs_tab(), "Logs")

        layout.addWidget(tabs)

        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)

def main():
    app = QApplication(sys.argv)

    # Create the qasync loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create and show window
    window = DanisenWindow()
    window.show()

    # Run the event loop
    with loop:
        loop.run_forever()

if __name__ == '__main__':
    main()