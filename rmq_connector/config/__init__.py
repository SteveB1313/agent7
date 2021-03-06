import os
import boto3
import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session

RDS = automap_base()
Base = declarative_base()

class Config():
    def __init__(self,base_dir):
      # --------------------------------- AWS Credentials
      APP_AWS_REGION = ""
      APP_AWS_KEY_ID = ""
      APP_AWS_SECRET_KEY = ""

      # --------------------------------- SQS QUEUE
      #self.queue_url = ""
      #self.max_messages = 10
      #self.vis_timeout = 5
      #self.sqs = boto3.client('sqs',region_name=APP_AWS_REGION,
      #  aws_access_key_id=APP_AWS_KEY_ID,aws_secret_access_key=APP_AWS_SECRET_KEY)

      # --------------------------------- Local Ledger database
      db_uri = "sqlite:////{}/database/ledger.db".format(base_dir)
      engine = sqlalchemy.create_engine(db_uri)
      self.session = sqlalchemy.orm.scoped_session(sqlalchemy.orm.sessionmaker())
      self.session.configure(bind=engine, autoflush=False, expire_on_commit=False)
      # Base.metadata.drop_all(engine)
      Base.metadata.create_all(engine)

      # --------------------------------- Create connection to RDS
      rds_uri = 'postgresql://db1:db1@postgres_db/db1'
      rds_engine = sqlalchemy.create_engine(rds_uri)
      RDS.prepare(rds_engine,reflect=True)
      self.rds_session = Session(rds_engine)

      self.tables = {}
      for obj in RDS.classes:
          name = str(obj.__table__)
          table_object = getattr(RDS.classes,name)
          self.tables[name] = table_object

class Ledger(Base):
    __tablename__ = 'ledger'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    model = sqlalchemy.Column(sqlalchemy.String())
    message_id = sqlalchemy.Column(sqlalchemy.String(),unique=True)
    date_added = sqlalchemy.Column(sqlalchemy.DateTime, server_default=func.now())
    date_updated = sqlalchemy.Column(sqlalchemy.DateTime, onupdate=func.now())

class FullHashLedger(Base):
    __tablename__ = 'fullhashledger'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    model = sqlalchemy.Column(sqlalchemy.String())
    full_hash = sqlalchemy.Column(sqlalchemy.String(),unique=True)
    date_added = sqlalchemy.Column(sqlalchemy.DateTime, server_default=func.now())
    date_updated = sqlalchemy.Column(sqlalchemy.DateTime, onupdate=func.now())
