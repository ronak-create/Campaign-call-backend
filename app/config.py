# app/config.py
import os
from dotenv import load_dotenv
load_dotenv()

class Settings:

    def __init__(self):
        self.EXOTEL_API_KEY = os.getenv('EXOTEL_API_KEY')
        self.EXOTEL_API_TOKEN = os.getenv('EXOTEL_API_TOKEN')
        self.EXOTEL_SUBDOMAIN = os.getenv('EXOTEL_SUBDOMAIN')
        self.EXOTEL_ACCOUNT_SID = os.getenv('EXOTEL_ACCOUNT_SID')
        self.EXOTEL_APP_SID = os.getenv('EXOTEL_APP_SID')
        self.EXOTEL_CALLER_ID = os.getenv('EXOTEL_CALLER_ID')

        self.BACKEND_HOST = os.getenv('BACKEND_HOST', '0.0.0.0')
        self.BACKEND_PORT = int(os.getenv('BACKEND_PORT', '8000'))

        self.DB_PATH = os.getenv('DATABASE_PATH', 'call_campaign.db')
        self.CALL_INTERVAL_SECONDS = int(os.getenv('CALL_INTERVAL_SECONDS', '3'))
        self.CALL_DETAILS_FETCH_DELAY = int(os.getenv('CALL_DETAILS_FETCH_DELAY', '5'))
        
        self.REDIS_BROKER_URL = os.getenv('REDIS_BROKER_URL', 'redis://localhost:6379/0')
        self.REDIS_BACKEND_URL = os.getenv('REDIS_BACKEND_URL', 'redis://localhost:6379/1')


        # Optional: Validate required ones
        self._validate()

    def _validate(self):
        required = [
            self.EXOTEL_API_KEY,
            self.EXOTEL_API_TOKEN,
            self.EXOTEL_SUBDOMAIN,
            self.EXOTEL_ACCOUNT_SID,
        ]

        if not all(required):
            raise RuntimeError("Missing required EXOTEL environment variables.")


settings = Settings()
