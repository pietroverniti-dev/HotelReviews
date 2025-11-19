from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
UIds = os.getenv("UIds")
Pws = os.getenv("Pws")

connection_string = f"mongodb+srv://{UIds}:{Pws}@cluster0.geflqhy.mongodb.net/?appName=Cluster0"
client = MongoClient(connection_string)

db = client['Verniti']
