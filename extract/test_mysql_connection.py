import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


load_dotenv()

host = os.getenv("MYSQL_HOST")
port = os.getenv("MYSQL_PORT", "3306")
user = os.getenv("MYSQL_USER")
password = os.getenv("MYSQL_PASSWORD")
database = os.getenv("MYSQL_DATABASE")


connection_url = URL.create(
    drivername="mysql+pymysql",
    username=user,
    password=password,
    host=host,
    port=int(port),
    database=database,
)

engine = create_engine(connection_url)


try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT DATABASE()"))
        database_name = result.scalar()

        print("MySQL connection successful.")
        print(f"Connected database: {database_name}")

except Exception as error:
    print("MySQL connection failed.")
    print(f"Error: {error}")