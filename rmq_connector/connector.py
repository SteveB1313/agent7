from utils.dedup_creator import DedupCreator
from config import Config,Ledger,FullHashLedger
import json
import os
import time
import pika
import logging
import sys

class Connector():
    def __init__(self,app,auto_ack=False):
        self.auto_ack = auto_ack
        pass

    def run(self):
        '''run entire process. get --> forward --> delete'''
        while True:
            logging.info("Processing the queue")
            count = 0
            d_count = 0
            try:
                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(host='rabbitmq'))
                channel = connection.channel()
                channel.queue_declare(queue='agent7_queue',durable=True)

                channel.basic_consume(
                    queue='agent7_queue', on_message_callback=self.process_message, auto_ack=self.auto_ack)

            # Don't recover if connection was closed by broker
            except pika.exceptions.ConnectionClosedByBroker as e:
                logging.error("ConnectionClosedByBroker exception:{}".format(e))
                break
            except pika.exceptions.ChannelClosedByBroker as e:
                logging.error("ChannelClosedByBroker exception:{}".format(e))
            # Don't recover on channel errors
            except pika.exceptions.AMQPChannelError as e:
                logging.critical("AMQPChannelError exception:{}".format(e))
                break
            # Recover on all other connection errors
            except pika.exceptions.AMQPConnectionError:
                continue
            channel.start_consuming()

    def process_message(self,ch,method,properties,body):
        new = 0
        up = 0
        dup = 0
        model = properties.headers["model"]
        payload = json.loads(body)
        table = app.tables.get(model)
        doc_hash = True

        if not table:
            logging.warning("Missing table model: {}. Please add it to the RDS Mapper".format(model))
            return False

        if not isinstance(payload,list):
            payload = [payload]

        for data in payload:
            message_id,full_hash = self.create_message_id(model,data,doc_hash=doc_hash) # create message ID
            data["message_id"] = message_id
            if self.check_if_new_message(model,message_id): # unique message, insert to rds
                self.add_to_ledger(model,message_id)
                new+=1
                outcome = self.insert_to_rds(table,model,data)
            else: # update or duplicate
                if doc_hash and full_hash: # check if doc_hash exists. If so, the record is 100% duplicate
                    if not self.check_if_uniq_full_hash(model,full_hash):
                        dup+=1
                        outcome = "Duplicate record"
                    else: # other parts of message changed, update the document in rds
                        outcome = self.update_to_rds(table,message_id,model,data)
                        up+=1
                        self.add_to_full_hash_ledger(model,full_hash)
                else: # other parts of message changed, update the document in rds
                    up+=1
                    outcome = self.update_to_rds(table,message_id,model,data)
            if not outcome:
                logging.error("[{}] Error while processing record:{}".format(model,str(outcome)))
        logging.info("[{}] Processed {} records. Inserted {} new records. Performed {} updates. Ignored {} duplicates.".format(model,len(payload),new,up,dup))

        if not self.auto_ack:
            ch.basic_ack(delivery_tag = method.delivery_tag) # on success, delete from queue
        return True

    def insert_to_rds(self,table,model,data):
        try:
            app.rds_session.add(table(**data))
            app.rds_session.commit()
            return True
        except TypeError as e:
            logging.warning("TypeError: Field in record does not exist in target table. Error:{}".format(e))
        return False

    def update_to_rds(self,table,message_id,model,data):
        try:
            t_mid = getattr(table,"message_id")
            record = app.rds_session.query(table).filter(table.message_id == message_id).update(data)
            app.rds_session.commit()
#            else: # record doesnt exist, insert
#                self.insert_to_rds(table,record)
            return True
        except Exception as e:
            logging.warning("Exception while updating record in rds:{}".format(e))
            print("Exception while updating record in rds:{}".format(e))
        return False

    def delete_message(self,handle):
        '''delete message from sqs queue'''
        delete_message = app.sqs.delete_message(
            QueueUrl=app.queue_url,
            ReceiptHandle=handle
        )
        return True

    def create_message_id(self,model,record,doc_hash=None):
        '''create message id from record based on multiple fields. Used for dedup'''
        message = DedupCreator().create_message_id(model,record,doc_hash)
        return message

    def check_if_new_message(self,model,message_id):
        '''check if message ID exists in local ledger'''
        if not app.session.query(Ledger).filter(Ledger.message_id == message_id).first():
            return True
        return False

    def check_if_uniq_full_hash(self,model,full_hash):
        '''check if full hash of doc exists in FullHashLedger'''
        if not app.session.query(FullHashLedger).filter(FullHashLedger.full_hash == full_hash).first():
            return True
        return False

    def add_to_ledger(self,model,message_id):
        '''add a message ID to local ledger'''
        record = Ledger(model=model,message_id=message_id)
        app.session.add(record)
        app.session.commit()
        return True

    def add_to_full_hash_ledger(self,model,full_hash):
        '''add a full hash to full hash ledger'''
        record = FullHashLedger(model=model,full_hash=full_hash)
        app.session.add(record)
        app.session.commit()
        return True


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logging.info("Starting the connector")
    base_dir = os.path.abspath(os.path.dirname(__file__))
    app = Config(base_dir)

    if not app.tables:
        logging.critical("Agent7 database is not ready. Exiting...")
    else:
        # Start Connector service
        Connector(app).run()
